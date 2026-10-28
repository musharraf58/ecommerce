from app.models import Category, Product, User, UserRole
from app.security import verify_password
from scripts.seed import CATALOG, seed_catalog, seed_users

ENV = {
    "SEED_ADMIN_EMAIL": "seed-admin@example.com",
    "SEED_ADMIN_PASSWORD": "admin-test-pass",
    "SEED_CUSTOMER_EMAIL": "seed-customer@example.com",
    "SEED_CUSTOMER_PASSWORD": "customer-test-pass",
}


def run_seed(db):
    seed_users(db, ENV)
    seed_catalog(db)


def test_seed_twice_creates_no_duplicates(db_session):
    run_seed(db_session)
    run_seed(db_session)

    expected_products = sum(len(products) for _, products in CATALOG.values())
    assert db_session.query(User).count() == 2
    assert db_session.query(Category).count() == len(CATALOG)
    assert db_session.query(Product).count() == expected_products


def test_seed_users_roles_and_hashed_passwords(db_session):
    run_seed(db_session)

    admin = db_session.query(User).filter_by(email=ENV["SEED_ADMIN_EMAIL"]).one()
    customer = db_session.query(User).filter_by(email=ENV["SEED_CUSTOMER_EMAIL"]).one()
    assert admin.role == UserRole.admin
    assert customer.role == UserRole.customer
    assert admin.hashed_password != ENV["SEED_ADMIN_PASSWORD"]
    assert verify_password(ENV["SEED_ADMIN_PASSWORD"], admin.hashed_password)
