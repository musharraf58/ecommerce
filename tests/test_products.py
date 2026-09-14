import uuid


def _get_admin_token(client):
    """Helper: register a user, promote to admin directly via DB, log in, return token."""
    client.post("/auth/register", json={"email": "admin@example.com", "password": "adminpass123"})

    # Promote directly via the test DB session isn't accessible here,
    # so we patch role through a second approach: create user then flip role in DB.
    from app.database import get_db
    from app.main import app
    from app.models import User, UserRole

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    user = db.query(User).filter(User.email == "admin@example.com").first()
    user.role = UserRole.admin
    db.commit()

    login_response = client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    return login_response.json()["access_token"]


def _get_customer_token(client):
    client.post("/auth/register", json={"email": "customer@example.com", "password": "customerpass123"})
    login_response = client.post("/auth/login", json={"email": "customer@example.com", "password": "customerpass123"})
    return login_response.json()["access_token"]


def test_create_product_as_admin(client):
    token = _get_admin_token(client)
    response = client.post(
        "/products",
        json={"name": "Laptop", "price": "999.99", "sku": "SKU-001", "stock_quantity": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Laptop"


def test_create_product_as_customer_forbidden(client):
    token = _get_customer_token(client)
    response = client.post(
        "/products",
        json={"name": "Laptop", "price": "999.99", "sku": "SKU-002", "stock_quantity": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_create_product_duplicate_sku(client):
    token = _get_admin_token(client)
    client.post(
        "/products",
        json={"name": "Laptop", "price": "999.99", "sku": "SKU-DUP", "stock_quantity": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    response = client.post(
        "/products",
        json={"name": "Another Laptop", "price": "500.00", "sku": "SKU-DUP", "stock_quantity": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_list_products_public(client):
    token = _get_admin_token(client)
    client.post(
        "/products",
        json={"name": "Phone", "price": "599.99", "sku": "SKU-003", "stock_quantity": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    response = client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


def test_search_products(client):
    token = _get_admin_token(client)
    client.post(
        "/products",
        json={"name": "Gaming Mouse", "price": "49.99", "sku": "SKU-004", "stock_quantity": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    response = client.get("/products?search=Gaming")
    assert response.status_code == 200
    data = response.json()
    assert any("Gaming" in item["name"] for item in data["items"])


def test_update_product(client):
    token = _get_admin_token(client)
    create_response = client.post(
        "/products",
        json={"name": "Keyboard", "price": "79.99", "sku": "SKU-005", "stock_quantity": 15},
        headers={"Authorization": f"Bearer {token}"},
    )
    product_id = create_response.json()["id"]

    update_response = client.patch(
        f"/products/{product_id}",
        json={"price": "69.99"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["price"] == "69.99"


def test_delete_product(client):
    token = _get_admin_token(client)
    create_response = client.post(
        "/products",
        json={"name": "Monitor", "price": "199.99", "sku": "SKU-006", "stock_quantity": 8},
        headers={"Authorization": f"Bearer {token}"},
    )
    product_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/products/{product_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204

    get_response = client.get(f"/products/{product_id}")
    assert get_response.status_code == 404


def test_get_nonexistent_product(client):
    fake_id = uuid.uuid4()
    response = client.get(f"/products/{fake_id}")
    assert response.status_code == 404


def test_create_category_as_admin(client):
    token = _get_admin_token(client)
    response = client.post(
        "/categories",
        json={"name": "Electronics"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Electronics"


def test_list_categories_public(client):
    token = _get_admin_token(client)
    client.post(
        "/categories",
        json={"name": "Books"},
        headers={"Authorization": f"Bearer {token}"},
    )
    response = client.get("/categories")
    assert response.status_code == 200
    assert any(c["name"] == "Books" for c in response.json())