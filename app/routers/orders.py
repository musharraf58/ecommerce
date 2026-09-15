import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, OrderItem, Cart, Product, User, OrderStatus, UserRole
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