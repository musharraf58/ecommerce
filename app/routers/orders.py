import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, OrderItem, Cart, Payment, PaymentStatus, Product, User, OrderStatus, UserRole
from app.schemas import OrderOut, OrderStatusUpdate
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/orders", tags=["orders"])

# Valid status transitions: current -> allowed next statuses
ALLOWED_TRANSITIONS = {
    OrderStatus.pending: {OrderStatus.paid, OrderStatus.cancelled},
    OrderStatus.paid: {OrderStatus.shipped, OrderStatus.cancelled},
    OrderStatus.shipped: set(),
    OrderStatus.cancelled: set(),
}


@router.post("/checkout", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def checkout(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if not cart or not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Lock each product row involved, in a consistent order (by id) to avoid deadlocks
    # when multiple checkouts touch overlapping products at the same time.
    product_ids = sorted({item.product_id for item in cart.items}, key=str)
    locked_products = {
        p.id: p
        for p in db.query(Product)
        .filter(Product.id.in_(product_ids))
        .with_for_update()
        .all()
    }

    total = 0
    order_items_to_create = []

    for cart_item in cart.items:
        product = locked_products[cart_item.product_id]

        if not product.is_active:
            raise HTTPException(status_code=400, detail=f"{product.name} is no longer available")

        if cart_item.quantity > product.stock_quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Only {product.stock_quantity} of {product.name} in stock",
            )

        product.stock_quantity -= cart_item.quantity
        total += product.price * cart_item.quantity

        order_items_to_create.append(
            OrderItem(
                product_id=product.id,
                quantity=cart_item.quantity,
                price_at_purchase=product.price,
            )
        )

    order = Order(user_id=user.id, status=OrderStatus.pending, total_amount=total)
    order.items = order_items_to_create
    db.add(order)

    # Clear the cart now that it's been converted into an order
    for item in list(cart.items):
        db.delete(item)

    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderOut])
def list_my_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    return order


@router.post(
    "/{order_id}/cancel",
    response_model=OrderOut,
    summary="Cancel my pending order",
    responses={
        401: {"description": "Missing or invalid credentials"},
        404: {"description": "Order not found, or it belongs to another user"},
        409: {"description": "Order is not pending, or its payment is already in progress"},
        502: {"description": "The Stripe PaymentIntent could not be cancelled"},
    },
)
def cancel_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 404 for both "doesn't exist" and "belongs to someone else" so existence isn't revealed
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=409, detail="Only pending orders can be cancelled")

    # Atomically claim the cancellation. Only the request that flips pending -> cancelled
    # continues, so a concurrent double-cancel can never restore stock twice.
    claimed = (
        db.query(Order)
        .filter(Order.id == order.id, Order.status == OrderStatus.pending)
        .update({Order.status: OrderStatus.cancelled}, synchronize_session=False)
    )
    if not claimed:
        db.rollback()
        raise HTTPException(status_code=409, detail="Only pending orders can be cancelled")

    # Lock products in the same order as checkout (by id) before restoring stock
    product_ids = sorted({item.product_id for item in order.items}, key=str)
    locked_products = {
        p.id: p
        for p in db.query(Product)
        .filter(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
        .all()
    }
    for item in order.items:
        locked_products[item.product_id].stock_quantity += item.quantity

    # Cancel any open PaymentIntent so the customer can't pay for a cancelled order
    payment = db.query(Payment).filter(Payment.order_id == order.id).first()
    if payment and payment.status != PaymentStatus.succeeded:
        try:
            stripe.PaymentIntent.cancel(payment.stripe_payment_intent_id)
        except stripe.error.InvalidRequestError:
            # Either already cancelled (fine, e.g. a retry) or not cancellable (payment in flight)
            try:
                intent = stripe.PaymentIntent.retrieve(payment.stripe_payment_intent_id)
                already_cancelled = intent.status == "canceled"
            except stripe.error.StripeError:
                already_cancelled = False
            if not already_cancelled:
                db.rollback()
                raise HTTPException(status_code=409, detail="Payment already in progress, order cannot be cancelled")
        except stripe.error.StripeError:
            db.rollback()
            raise HTTPException(status_code=502, detail="Could not cancel the payment, please try again")
        payment.status = PaymentStatus.failed

    db.commit()
    db.refresh(order)
    return order


@router.get("/admin/all", response_model=list[OrderOut])
def list_all_orders(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Order).order_by(Order.created_at.desc()).all()


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: uuid.UUID,
    status_update: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    allowed_next = ALLOWED_TRANSITIONS.get(order.status, set())
    if status_update.status not in allowed_next:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {order.status.value} to {status_update.status.value}",
        )

    order.status = status_update.status
    db.commit()
    db.refresh(order)
    return order