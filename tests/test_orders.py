import threading
import uuid


def _get_customer_token(client, email):
    client.post("/auth/register", json={"email": email, "password": "pass12345"})
    login_response = client.post("/auth/login", json={"email": email, "password": "pass12345"})
    return login_response.json()["access_token"]


def _get_admin_token(client, email="ordersadmin@example.com"):
    client.post("/auth/register", json={"email": email, "password": "adminpass123"})

    from app.database import get_db
    from app.main import app
    from app.models import User, UserRole

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user = db.query(User).filter(User.email == email).first()
    user.role = UserRole.admin
    db.commit()

    login_response = client.post("/auth/login", json={"email": email, "password": "adminpass123"})
    return login_response.json()["access_token"]


def _create_product(client, admin_token, sku, stock):
    response = client.post(
        "/products",
        json={"name": "Order Test Product", "price": "20.00", "sku": sku, "stock_quantity": stock},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return response.json()["id"]


def _add_to_cart(client, token, product_id, quantity):
    client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": quantity},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_checkout_empty_cart_fails(client):
    token = _get_customer_token(client, "emptycart@example.com")
    response = client.post("/orders/checkout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400


def test_successful_checkout(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-1", 10)

    customer_token = _get_customer_token(client, "checkout1@example.com")
    _add_to_cart(client, customer_token, product_id, 2)

    response = client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert float(data["total_amount"]) == 40.00
    assert len(data["items"]) == 1


def test_checkout_decrements_stock(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-2", 10)

    customer_token = _get_customer_token(client, "checkout2@example.com")
    _add_to_cart(client, customer_token, product_id, 3)
    client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})

    product_response = client.get(f"/products/{product_id}")
    assert product_response.json()["stock_quantity"] == 7


def test_checkout_clears_cart(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-3", 10)

    customer_token = _get_customer_token(client, "checkout3@example.com")
    _add_to_cart(client, customer_token, product_id, 1)
    client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})

    cart_response = client.get("/cart", headers={"Authorization": f"Bearer {customer_token}"})
    assert cart_response.json()["items"] == []


def test_checkout_fails_when_exceeding_stock(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-4", 2)

    customer_token = _get_customer_token(client, "checkout4@example.com")
    _add_to_cart(client, customer_token, product_id, 2)

    # Manually shrink stock after adding to cart, to simulate another buyer taking it first
    from app.database import get_db
    from app.main import app
    from app.models import Product

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    product = db.query(Product).filter(Product.id == uuid.UUID(product_id)).first()
    product.stock_quantity = 0
    db.commit()

    response = client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})
    assert response.status_code == 400


def test_list_my_orders(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-5", 10)

    customer_token = _get_customer_token(client, "checkout5@example.com")
    _add_to_cart(client, customer_token, product_id, 1)
    client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})

    response = client.get("/orders", headers={"Authorization": f"Bearer {customer_token}"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_cannot_view_others_order(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-6", 10)

    token_a = _get_customer_token(client, "ordera@example.com")
    _add_to_cart(client, token_a, product_id, 1)
    order_response = client.post("/orders/checkout", headers={"Authorization": f"Bearer {token_a}"})
    order_id = order_response.json()["id"]

    token_b = _get_customer_token(client, "orderb@example.com")
    response = client.get(f"/orders/{order_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert response.status_code == 403


def test_admin_can_view_all_orders(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-7", 10)

    customer_token = _get_customer_token(client, "checkout7@example.com")
    _add_to_cart(client, customer_token, product_id, 1)
    client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})

    response = client.get("/orders/admin/all", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_valid_status_transition(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-8", 10)

    customer_token = _get_customer_token(client, "checkout8@example.com")
    _add_to_cart(client, customer_token, product_id, 1)
    order_response = client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})
    order_id = order_response.json()["id"]

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "paid"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "paid"


def test_invalid_status_transition_rejected(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, "ORDER-SKU-9", 10)

    customer_token = _get_customer_token(client, "checkout9@example.com")
    _add_to_cart(client, customer_token, product_id, 1)
    order_response = client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})
    order_id = order_response.json()["id"]

    # pending -> shipped is not allowed (must go through paid first)
    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "shipped"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400