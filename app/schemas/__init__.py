import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models import UserRole
from decimal import Decimal
from typing import Optional, List


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