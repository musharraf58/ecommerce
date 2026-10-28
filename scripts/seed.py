"""Seed the database with demo users and sample products.

Usage: python -m scripts.seed

Safe to run repeatedly: existing users, categories and products are skipped.
Credentials are read from SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD,
SEED_CUSTOMER_EMAIL and SEED_CUSTOMER_PASSWORD.
"""
import os
import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Category, Product, User, UserRole
from app.security import hash_password

REQUIRED_ENV = (
    "SEED_ADMIN_EMAIL",
    "SEED_ADMIN_PASSWORD",
    "SEED_CUSTOMER_EMAIL",
    "SEED_CUSTOMER_PASSWORD",
)

# category name -> (sku prefix, [(name, description, price, stock)])
CATALOG = {
    "Kitchen": ("KIT", [
        ("Maplewood Cutting Board", "Thick end-grain board with a juice groove.", "34.90", 45),
        ("Copperline Saucepan", "Two-litre saucepan with a heat-safe handle.", "42.00", 30),
        ("Ember Cast Skillet", "Pre-seasoned 26 cm cast iron skillet.", "39.50", 25),
        ("Willow Spice Rack", "Rotating rack with twelve glass jars.", "27.75", 60),
        ("Harbor Stoneware Mug Set", "Set of four 350 ml glazed mugs.", "24.00", 80),
    ]),
    "Outdoors": ("OUT", [
        ("Trailmark Daypack 24L", "Lightweight pack with rain cover and hip belt.", "64.00", 40),
        ("Summit Folding Camp Stool", "Compact aluminium stool, holds 110 kg.", "29.95", 55),
        ("Pinecone Insulated Bottle", "750 ml double-wall steel bottle.", "22.50", 120),
        ("Northwind Packable Rain Shell", "Waterproof jacket that stuffs into its pocket.", "89.00", 18),
        ("Fernhollow Hammock", "Double parachute-nylon hammock with straps.", "36.40", 35),
    ]),
    "Stationery": ("STA", [
        ("Lumen Dot-Grid Notebook", "A5 notebook, 160 pages of 100 gsm paper.", "12.80", 200),
        ("Quillfeather Gel Pens (6)", "Smooth 0.5 mm gel pens in assorted inks.", "8.95", 300),
        ("Birchbark Desk Planner", "Undated weekly planner with a linen cover.", "18.25", 90),
        ("Tidewater Sticky Flags", "Pack of 200 repositionable page flags.", "4.50", 500),
        ("Oakline Pencil Case", "Waxed canvas case with a brass zipper.", "14.00", 75),
    ]),
    "Home Office": ("OFF", [
        ("Aspen Laptop Riser", "Adjustable aluminium stand for 13-17 inch laptops.", "46.00", 50),
        ("Cedar Monitor Shelf", "Solid wood shelf with two cable cut-outs.", "52.90", 28),
        ("Slate Cable Organiser Kit", "Silicone clips and ties for a tidy desk.", "11.99", 150),
        ("Meadow Desk Lamp", "Dimmable LED lamp with three colour modes.", "38.75", 65),
        ("Harvest Ergonomic Footrest", "Tilting footrest with a textured surface.", "31.20", 0),
    ]),
}


def read_env() -> dict[str, str]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")
    return {name: os.environ[name] for name in REQUIRED_ENV}


def seed_users(db: Session, env: dict[str, str]) -> int:
    created = 0
    accounts = (
        (env["SEED_ADMIN_EMAIL"], env["SEED_ADMIN_PASSWORD"], UserRole.admin),
        (env["SEED_CUSTOMER_EMAIL"], env["SEED_CUSTOMER_PASSWORD"], UserRole.customer),
    )
    for email, password, role in accounts:
        if db.query(User).filter(User.email == email).first():
            continue
        db.add(User(email=email, hashed_password=hash_password(password), role=role))
        created += 1
    db.commit()
    return created


def seed_catalog(db: Session) -> tuple[int, int]:
    categories_created = products_created = 0
    for category_name, (prefix, products) in CATALOG.items():
        category = db.query(Category).filter(Category.name == category_name).first()
        if not category:
            category = Category(name=category_name)
            db.add(category)
            db.flush()
            categories_created += 1
        for index, (name, description, price, stock) in enumerate(products, start=1):
            sku = f"{prefix}-{index:03d}"
            if db.query(Product).filter(Product.sku == sku).first():
                continue
            db.add(Product(
                name=name,
                description=description,
                price=Decimal(price),
                sku=sku,
                category_id=category.id,
                stock_quantity=stock,
            ))
            products_created += 1
    db.commit()
    return categories_created, products_created


def main() -> None:
    env = read_env()
    with SessionLocal() as db:
        users = seed_users(db, env)
        categories, products = seed_catalog(db)
    print(f"Created {users} users, {categories} categories, {products} products.")


if __name__ == "__main__":
    main()
