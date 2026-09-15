from unittest.mock import patch, MagicMock


def _get_customer_token(client, email):
    client.post("/auth/register", json={"email": email, "password": "pass12345"})
    login_response = client.post("/auth/login", json={"email": email, "password": "pass12345"})
    return login_response.json()["access_token"]


def _get_admin_token(client, email="paymentsadmin@example.com"):
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


def _create_paid_ready_order(client, email_suffix):
    admin_token = _get_admin_token(client, f"payadmin{email_suffix}@example.com")

    product_response = client.post(
        "/products",
        json={"name": "Payment Test Product", "price": "15.00", "sku": f"PAY-SKU-{email_suffix}", "stock_quantity": 10},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    product_id = product_response.json()["id"]

    customer_token = _get_customer_token(client, f"paycust{email_suffix}@example.com")
    client.post(
        "/cart/items",
        json={"product_id": product_id, "quantity": 1},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    order_response = client.post("/orders/checkout", headers={"Authorization": f"Bearer {customer_token}"})
    return order_response.json()["id"], customer_token


@patch("app.routers.payments.stripe.PaymentIntent.create")
def test_create_payment_intent(mock_create, client):
    mock_create.return_value = MagicMock(id="pi_test_123", client_secret="pi_test_123_secret_abc")

    order_id, customer_token = _create_paid_ready_order(client, "1")

    response = client.post(
        f"/payments/orders/{order_id}/create-intent",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["client_secret"] == "pi_test_123_secret_abc"


@patch("app.routers.payments.stripe.PaymentIntent.retrieve")
@patch("app.routers.payments.stripe.PaymentIntent.create")
def test_create_intent_is_idempotent(mock_create, mock_retrieve, client):
    mock_create.return_value = MagicMock(id="pi_test_456", client_secret="pi_test_456_secret_abc")
    mock_retrieve.return_value = MagicMock(client_secret="pi_test_456_secret_abc")

    order_id, customer_token = _create_paid_ready_order(client, "2")

    first = client.post(
        f"/payments/orders/{order_id}/create-intent",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    second = client.post(
        f"/payments/orders/{order_id}/create-intent",
        headers={"Authorization": f"Bearer {customer_token}"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    mock_create.assert_called_once()


@patch("app.routers.payments.stripe.PaymentIntent.create")
def test_cannot_create_intent_for_others_order(mock_create, client):
    mock_create.return_value = MagicMock(id="pi_test_789", client_secret="pi_test_789_secret_abc")

    order_id, _ = _create_paid_ready_order(client, "3")
    other_token = _get_customer_token(client, "otherpayuser@example.com")

    response = client.post(
        f"/payments/orders/{order_id}/create-intent",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


@patch("app.routers.payments.stripe.Webhook.construct_event")
def test_webhook_payment_succeeded_updates_order(mock_construct_event, client):
    with patch("app.routers.payments.stripe.PaymentIntent.create") as mock_create:
        mock_create.return_value = MagicMock(id="pi_webhook_test", client_secret="pi_webhook_test_secret_abc")
        order_id, customer_token = _create_paid_ready_order(client, "4")
        client.post(
            f"/payments/orders/{order_id}/create-intent",
            headers={"Authorization": f"Bearer {customer_token}"},
        )

    mock_construct_event.return_value = {
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_webhook_test"}},
    }

    response = client.post(
        "/payments/webhook",
        content=b"{}",
        headers={"stripe-signature": "fake_signature_for_test"},
    )
    assert response.status_code == 200

    order_response = client.get(
        f"/orders/{order_id}",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert order_response.json()["status"] == "paid"


@patch("app.routers.payments.stripe.Webhook.construct_event")
def test_webhook_invalid_signature_rejected(mock_construct_event, client):
    import stripe as stripe_module
    mock_construct_event.side_effect = stripe_module.error.SignatureVerificationError("bad sig", "sig_header")

    response = client.post(
        "/payments/webhook",
        content=b"{}",
        headers={"stripe-signature": "invalid"},
    )
    assert response.status_code == 400