import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models import UserRole
from decimal import Decimal
from typing import Optional, List
from app.models import OrderStatus


class CategoryCreate(BaseModel):
    name: str
    parent_category_id: Optional[uuid.UUID] = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    parent_category_id: Optional[uuid.UUID]

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: Decimal
    sku: str
    category_id: Optional[uuid.UUID] = None
    stock_quantity: int = 0
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    category_id: Optional[uuid.UUID] = None
    stock_quantity: Optional[int] = None
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    price: Decimal
    sku: str
    category_id: Optional[uuid.UUID]
    stock_quantity: int
    is_active: bool

    class Config:
        from_attributes = True


class ProductListOut(BaseModel):
    total: int
    items: List[ProductOut]

class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CartItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = 1


class CartItemUpdate(BaseModel):
    quantity: int


class CartItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    product: ProductOut

    class Config:
        from_attributes = True


class CartOut(BaseModel):
    id: uuid.UUID
    items: List[CartItemOut]

    class Config:
        from_attributes = True


class OrderItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    price_at_purchase: Decimal
    product: ProductOut

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    total_amount: Decimal
    created_at: datetime
    items: List[OrderItemOut]

    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    status: OrderStatus