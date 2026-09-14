import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cart, CartItem, Product, User
from app.schemas import CartItemAdd, CartItemUpdate, CartOut
from app.dependencies import get_current_user

router = APIRouter(prefix="/cart", tags=["cart"])


def _get_or_create_cart(db: Session, user: User) -> Cart:
    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if not cart:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


@router.get("", response_model=CartOut)
def get_cart(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cart = _get_or_create_cart(db, user)
    return cart


@router.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_item(
    item_in: CartItemAdd,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = db.query(Product).filter(
        Product.id == item_in.product_id, Product.is_active == True
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if item_in.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

    cart = _get_or_create_cart(db, user)

    existing_item = db.query(CartItem).filter(
        CartItem.cart_id == cart.id, CartItem.product_id == product.id
    ).first()

    requested_total = item_in.quantity + (existing_item.quantity if existing_item else 0)
    if requested_total > product.stock_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product.stock_quantity} in stock",
        )

    if existing_item:
        existing_item.quantity = requested_total
    else:
        db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=item_in.quantity))

    db.commit()
    db.refresh(cart)
    return cart


@router.patch("/items/{item_id}", response_model=CartOut)
def update_item(
    item_id: uuid.UUID,
    item_in: CartItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cart = _get_or_create_cart(db, user)
    item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if item_in.quantity < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

    if item_in.quantity > item.product.stock_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {item.product.stock_quantity} in stock",
        )

    item.quantity = item_in.quantity
    db.commit()
    db.refresh(cart)
    return cart


@router.delete("/items/{item_id}", response_model=CartOut)
def remove_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cart = _get_or_create_cart(db, user)
    item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.delete(item)
    db.commit()
    db.refresh(cart)
    return cart