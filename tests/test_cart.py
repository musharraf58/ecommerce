def _get_customer_token(client, email="cartuser@example.com"):
    client.post("/auth/register", json={"email": email, "password": "pass12345"})
    login_response = client.post("/auth/login", json={"email": email, "password": "pass12345"})
    return login_response.json()["access_token"]


def _get_admin_token(client):
    client.post("/auth/register", json={"email": "cartadmin@example.com", "password": "adminpass123"})

    from app.database import get_db
    from app.main import app
    from app.models import User, UserRole

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user = db.query(User).filter(User.email == "cartadmin@example.com").first()
    user.role = UserRole.admin
    db.commit()

    login_response = client.post("/auth/login", json={"email": "cartadmin@example.com", "password": "adminpass123"})
    return login_response.json()["access_token"]


def _create_product(client, admin_token, sku="CART-SKU-1", stock=10):
    response = client.post(
        "/products",
        json={"name": "Test Product", "price": "10.00", "sku": sku, "stock_quantity": stock},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return response.json()["id"]


def test_get_cart_auto_creates(client):
    token = _get_customer_token(client)
    response = client.get("/cart", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_add_item_to_cart(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, sku="CART-SKU-2", stock=10)

    customer_token = _get_customer_token(client, email="cart2@example.com")
    response = client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 2},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 201
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["quantity"] == 2


def test_add_item_exceeding_stock(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, sku="CART-SKU-3", stock=5)

    customer_token = _get_customer_token(client, email="cart3@example.com")
    response = client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 10},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 400


def test_add_same_product_twice_combines_quantity(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, sku="CART-SKU-4", stock=10)

    customer_token = _get_customer_token(client, email="cart4@example.com")
    client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 2},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    response = client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 3},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 201
    assert response.json()["items"][0]["quantity"] == 5


def test_update_cart_item_quantity(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, sku="CART-SKU-5", stock=10)

    customer_token = _get_customer_token(client, email="cart5@example.com")
    add_response = client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 2},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    item_id = add_response.json()["items"][0]["id"]

    update_response = client.patch(
        f"/cart/items/{item_id}",
        json={"quantity": 4},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["items"][0]["quantity"] == 4


def test_remove_cart_item(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, sku="CART-SKU-6", stock=10)

    customer_token = _get_customer_token(client, email="cart6@example.com")
    add_response = client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 1},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    item_id = add_response.json()["items"][0]["id"]

    remove_response = client.delete(
        f"/cart/items/{item_id}",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert remove_response.status_code == 200
    assert remove_response.json()["items"] == []


def test_cart_is_isolated_per_user(client):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, sku="CART-SKU-7", stock=10)

    token_a = _get_customer_token(client, email="usera@example.com")
    token_b = _get_customer_token(client, email="userb@example.com")

    client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 1},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    cart_b = client.get("/cart", headers={"Authorization": f"Bearer {token_b}"})
    assert cart_b.json()["items"] == []