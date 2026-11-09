import threading
import uuid
from unittest.mock import MagicMock, patch

import stripe as stripe_module
from fastapi.testclient import TestClient

from tests.test_orders import (
    _add_to_cart,
    _create_product,
    _get_admin_token,
    _get_customer_token,
)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _place_order(client, sku, email, stock=10, quantity=3):
    admin_token = _get_admin_token(client)
    product_id = _create_product(client, admin_token, sku, stock)
    token = _get_customer_token(client, email)
    _add_to_cart(client, token, product_id, quantity)
    response = client.post("/orders/checkout", headers=_auth(token))
    return response.json()["id"], product_id, token


def _stock(client, product_id):
    return client.get(f"/products/{product_id}").json()["stock_quantity"]


def _set_status(client, order_id, new_status):
    from app.database import get_db
    from app.main import app
    from app.models import Order, OrderStatus

    db = next(app.dependency_overrides[get_db]())
    order = db.query(Order).filter(Order.id == uuid.UUID(order_id)).first()
    order.status = OrderStatus(new_status)
    db.commit()


def test_owner_cancels_pending_order_and_stock_is_restored(client):
    order_id, product_id, token = _place_order(client, "CANCEL-SKU-1", "cancel1@example.com")
    assert _stock(client, product_id) == 7

    response = client.post(f"/orders/{order_id}/cancel", headers=_auth(token))

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["status"] == "cancelled"
    assert _stock(client, product_id) == 10


def test_cancel_other_users_order_returns_404(client):
    order_id, product_id, _ = _place_order(client, "CANCEL-SKU-2", "cancel2a@example.com")
    other_token = _get_customer_token(client, "cancel2b@example.com")

    response = client.post(f"/orders/{order_id}/cancel", headers=_auth(other_token))

    assert response.status_code == 404
    assert _stock(client, product_id) == 7


def test_cancel_unknown_order_returns_404(client):
    token = _get_customer_token(client, "cancel3@example.com")
    response = client.post(f"/orders/{uuid.uuid4()}/cancel", headers=_auth(token))
    assert response.status_code == 404


def test_cancel_paid_and_shipped_orders_return_409(client):
    for status, suffix in (("paid", "4a"), ("shipped", "4b")):
        order_id, product_id, token = _place_order(
            client, f"CANCEL-SKU-{suffix}", f"cancel{suffix}@example.com"
        )
        _set_status(client, order_id, status)

        response = client.post(f"/orders/{order_id}/cancel", headers=_auth(token))

        assert response.status_code == 409
        assert response.json()["detail"] == "Only pending orders can be cancelled"
        assert _stock(client, product_id) == 7


def test_cancel_already_cancelled_order_returns_409_and_does_not_restore_twice(client):
    order_id, product_id, token = _place_order(client, "CANCEL-SKU-5", "cancel5@example.com")
    assert client.post(f"/orders/{order_id}/cancel", headers=_auth(token)).status_code == 200

    response = client.post(f"/orders/{order_id}/cancel", headers=_auth(token))

    assert response.status_code == 409
    assert _stock(client, product_id) == 10


def test_cancel_requires_authentication(client):
    response = client.post(f"/orders/{uuid.uuid4()}/cancel")
    assert response.status_code == 401


@patch("app.routers.orders.stripe.PaymentIntent.cancel")
@patch("app.routers.payments.stripe.PaymentIntent.create")
def test_cancel_cancels_open_payment_intent(mock_create, mock_cancel, client):
    mock_create.return_value = MagicMock(id="pi_cancel_1", client_secret="secret")
    order_id, product_id, token = _place_order(client, "CANCEL-SKU-6", "cancel6@example.com")
    client.post(f"/payments/orders/{order_id}/create-intent", headers=_auth(token))

    response = client.post(f"/orders/{order_id}/cancel", headers=_auth(token))

    assert response.status_code == 200
    mock_cancel.assert_called_once_with("pi_cancel_1")
    assert _stock(client, product_id) == 10


@patch("app.routers.orders.stripe.PaymentIntent.retrieve")
@patch("app.routers.orders.stripe.PaymentIntent.cancel")
@patch("app.routers.payments.stripe.PaymentIntent.create")
def test_cancel_rejected_when_payment_already_in_progress(
    mock_create, mock_cancel, mock_retrieve, client
):
    mock_create.return_value = MagicMock(id="pi_cancel_2", client_secret="secret")
    mock_cancel.side_effect = stripe_module.error.InvalidRequestError("not cancellable", "id")
    mock_retrieve.return_value = MagicMock(status="succeeded")
    order_id, product_id, token = _place_order(client, "CANCEL-SKU-7", "cancel7@example.com")
    client.post(f"/payments/orders/{order_id}/create-intent", headers=_auth(token))

    response = client.post(f"/orders/{order_id}/cancel", headers=_auth(token))

    assert response.status_code == 409
    assert _stock(client, product_id) == 7
    order = client.get(f"/orders/{order_id}", headers=_auth(token)).json()
    assert order["status"] == "pending"


@patch("app.routers.orders.stripe.PaymentIntent.retrieve")
@patch("app.routers.orders.stripe.PaymentIntent.cancel")
@patch("app.routers.payments.stripe.PaymentIntent.create")
def test_cancel_retry_succeeds_when_intent_already_cancelled(
    mock_create, mock_cancel, mock_retrieve, client
):
    mock_create.return_value = MagicMock(id="pi_cancel_3", client_secret="secret")
    mock_cancel.side_effect = stripe_module.error.InvalidRequestError("already canceled", "id")
    mock_retrieve.return_value = MagicMock(status="canceled")
    order_id, product_id, token = _place_order(client, "CANCEL-SKU-8", "cancel8@example.com")
    client.post(f"/payments/orders/{order_id}/create-intent", headers=_auth(token))

    response = client.post(f"/orders/{order_id}/cancel", headers=_auth(token))

    assert response.status_code == 200
    assert _stock(client, product_id) == 10


@patch("app.routers.payments.stripe.Webhook.construct_event")
@patch("app.routers.orders.stripe.PaymentIntent.cancel")
@patch("app.routers.payments.stripe.PaymentIntent.create")
def test_late_payment_webhook_does_not_reopen_cancelled_order(
    mock_create, mock_cancel, mock_construct_event, client
):
    mock_create.return_value = MagicMock(id="pi_cancel_4", client_secret="secret")
    order_id, _, token = _place_order(client, "CANCEL-SKU-9", "cancel9@example.com")
    client.post(f"/payments/orders/{order_id}/create-intent", headers=_auth(token))
    client.post(f"/orders/{order_id}/cancel", headers=_auth(token))
    mock_construct_event.return_value = {
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_cancel_4"}},
    }

    response = client.post("/payments/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    assert response.status_code == 200
    order = client.get(f"/orders/{order_id}", headers=_auth(token)).json()
    assert order["status"] == "cancelled"


def test_concurrent_double_cancel_restores_stock_once(client, db_session):
    from app.database import get_db
    from app.main import app
    from tests.conftest import TestingSessionLocal

    order_id, product_id, token = _place_order(client, "CANCEL-SKU-10", "cancel10@example.com")
    db_session.commit()  # release any open read transaction before the threads write

    def per_request_session():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = per_request_session

    barrier = threading.Barrier(2)
    results = []

    def attempt():
        thread_client = TestClient(app)
        barrier.wait()
        results.append(thread_client.post(f"/orders/{order_id}/cancel", headers=_auth(token)).status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [200, 409]
    assert _stock(client, product_id) == 10
