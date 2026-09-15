import stripe,uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Order, Payment, PaymentStatus, OrderStatus, User
from app.schemas import PaymentOut
from app.dependencies import get_current_user

stripe.api_key = settings.stripe_secret_key

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/orders/{order_id}/create-intent", response_model=PaymentOut)
def create_payment_intent(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=400, detail="Order is not awaiting payment")

    existing_payment = db.query(Payment).filter(Payment.order_id == order.id).first()
    if existing_payment:
        intent = stripe.PaymentIntent.retrieve(existing_payment.stripe_payment_intent_id)
        return PaymentOut(
            id=existing_payment.id,
            order_id=order.id,
            status=existing_payment.status.value,
            amount=existing_payment.amount,
            client_secret=intent.client_secret,
        )

    intent = stripe.PaymentIntent.create(
        amount=int(order.total_amount * 100),  # Stripe expects the smallest currency unit (cents)
        currency="usd",
        metadata={"order_id": str(order.id)},
    )

    payment = Payment(
        order_id=order.id,
        stripe_payment_intent_id=intent.id,
        status=PaymentStatus.pending,
        amount=order.total_amount,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return PaymentOut(
        id=payment.id,
        order_id=order.id,
        status=payment.status.value,
        amount=payment.amount,
        client_secret=intent.client_secret,
    )


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        payment = db.query(Payment).filter(Payment.stripe_payment_intent_id == intent["id"]).first()
        if payment:
            payment.status = PaymentStatus.succeeded
            payment.order.status = OrderStatus.paid
            db.commit()

    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        payment = db.query(Payment).filter(Payment.stripe_payment_intent_id == intent["id"]).first()
        if payment:
            payment.status = PaymentStatus.failed
            db.commit()

    return {"status": "received"}