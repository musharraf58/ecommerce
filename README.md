# E-Commerce Backend API

[![CI](https://github.com/musharraf58/ecommerce/actions/workflows/ci.yml/badge.svg)](https://github.com/musharraf58/ecommerce/actions/workflows/ci.yml)

A production-structured REST API for an online store, built with FastAPI and PostgreSQL. Handles user accounts, product catalog, shopping carts, order processing with concurrency-safe inventory management, and Stripe payments.

## Features

**Authentication & Authorization**
- JWT-based auth with separate access (30 min) and refresh (7 day) tokens
- Bcrypt password hashing
- Role-based access control (customer / admin)
- Token type validation — a refresh token can't be used as an access token

**Product Catalog**
- Admin-only CRUD for products and categories
- Nested categories via self-referencing foreign key
- Public browsing with pagination, category filtering, price range filtering, and name search
- Soft deactivation (`is_active`) hides products from customers without deleting order history

**Shopping Cart**
- One persistent cart per user, created lazily on first use
- Stock availability validated on every add and update
- Adding an existing product increases its quantity rather than duplicating the row
- Carts are strictly scoped per user

**Orders & Inventory Integrity**
- Checkout converts cart → order in a single database transaction
- **Row-level locking (`SELECT ... FOR UPDATE`) prevents overselling under concurrent checkouts**
- Products locked in consistent sorted order to avoid deadlocks
- Price snapshotted at purchase time (`price_at_purchase`), so historical orders stay accurate when prices change
- Order status lifecycle enforced as a state machine (`pending → paid → shipped`, with `cancelled` reachable from `pending`/`paid`)

**Payments**
- Stripe PaymentIntent creation, scoped to the order's owner
- Idempotent — repeat calls return the existing intent rather than creating a duplicate charge
- Webhook handler with signature verification, updating payment and order status on success/failure

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL 16 |
| ORM / Migrations | SQLAlchemy 2.0 / Alembic |
| Caching & Sessions | Redis 7 |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Payments | Stripe |
| Testing | pytest, pytest-cov |
| Containerization | Docker, docker-compose |
| CI | GitHub Actions |

## Architecture

The application follows a layered structure:

```
app/
├── main.py           # App entry point, router registration
├── config.py         # Pydantic settings loaded from environment
├── database.py       # SQLAlchemy engine, session factory, get_db dependency
├── security.py       # Password hashing, JWT creation/decoding
├── dependencies.py   # Auth dependencies (get_current_user, require_admin)
├── models/           # SQLAlchemy ORM models
├── schemas/          # Pydantic request/response schemas
└── routers/          # API endpoints grouped by domain
    ├── auth.py
    ├── products.py
    ├── cart.py
    ├── orders.py
    └── payments.py
```

Dependency injection via FastAPI's `Depends` handles database sessions, current-user resolution, and role enforcement — each request gets its own session, guaranteed to close even on error.

## Design Decisions

**UUID primary keys instead of auto-incrementing integers.** Sequential IDs expose business information (how many orders exist, how fast you're growing) and are trivially enumerable in URLs. UUIDs avoid both issues.

**`Numeric(10, 2)` for all monetary values, never `Float`.** Floating-point arithmetic introduces rounding errors that compound across line items — unacceptable for money.

**Price snapshot on order items.** `OrderItem.price_at_purchase` stores what the customer actually paid. Joining to the live product price would silently rewrite order history whenever an admin changes a price.

**Row-level locking at checkout.** Without it, two concurrent requests can both read `stock_quantity = 1`, both pass the availability check, and both decrement — overselling the item. `SELECT ... FOR UPDATE` serializes access to the affected product rows, making check-then-decrement atomic. Products are locked in sorted order so that overlapping concurrent checkouts can't deadlock by acquiring locks in opposite sequences.

**Concurrency verified against real PostgreSQL, not the test suite.** The automated test suite runs against SQLite for speed and isolation, but SQLite doesn't implement row-level locking, so a concurrency test there would prove nothing. The overselling protection was instead verified by firing simultaneous checkouts against the live PostgreSQL container: one request succeeded with a created order, the other correctly received `400 — Only 0 in stock`.

## Getting Started

### Prerequisites
- Docker and Docker Compose
- A Stripe account (test mode) for payment features

### Setup

```bash
git clone https://github.com/musharraf58/ecommerce.git
cd ecommerce

cp .env.example .env
# Edit .env and fill in your values, especially STRIPE_SECRET_KEY

docker compose up --build
```

Run the database migrations:

```bash
docker compose run --rm api alembic upgrade head
```

The API will be available at `http://localhost:8000`, with interactive documentation at `http://localhost:8000/docs`.

### Running Tests

```bash
docker compose run --rm api pytest -v
```

### Testing Stripe Webhooks Locally

```bash
stripe login
stripe listen --forward-to localhost:8000/payments/webhook
```

Copy the printed `whsec_...` signing secret into your `.env` as `STRIPE_WEBHOOK_SECRET`, then restart the API.

## API Overview

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/auth/register` | Public | Create an account |
| POST | `/auth/login` | Public | Obtain access + refresh tokens |
| POST | `/auth/refresh` | Public | Exchange a refresh token for new tokens |
| GET | `/auth/me` | Authenticated | Current user's profile |
| GET | `/products` | Public | List products (paginated, filterable, searchable) |
| GET | `/products/{id}` | Public | Single product detail |
| POST | `/products` | Admin | Create a product |
| PATCH | `/products/{id}` | Admin | Partially update a product |
| DELETE | `/products/{id}` | Admin | Delete a product |
| GET | `/categories` | Public | List categories |
| POST | `/categories` | Admin | Create a category |
| GET | `/cart` | Authenticated | View cart (created on first access) |
| POST | `/cart/items` | Authenticated | Add a product to the cart |
| PATCH | `/cart/items/{id}` | Authenticated | Change an item's quantity |
| DELETE | `/cart/items/{id}` | Authenticated | Remove an item |
| POST | `/orders/checkout` | Authenticated | Convert cart into an order |
| GET | `/orders` | Authenticated | Own order history |
| GET | `/orders/{id}` | Owner or Admin | Single order detail |
| GET | `/orders/admin/all` | Admin | All orders |
| PATCH | `/orders/{id}/status` | Admin | Advance order status |
| POST | `/payments/orders/{id}/create-intent` | Owner | Create a Stripe PaymentIntent |
| POST | `/payments/webhook` | Stripe | Handle payment lifecycle events |

Full interactive documentation, including request and response schemas, is auto-generated at `/docs`.

## Testing

38 tests covering authentication flows, permission boundaries, catalog CRUD and filtering, cart stock validation and user isolation, checkout and inventory decrementing, order status transitions, and payment intent creation with mocked Stripe calls.

```bash
docker compose run --rm api pytest -v
```

## Roadmap

- Redis-backed rate limiting on authentication endpoints
- Redis caching for product listings with invalidation on write
- Structured logging
- Product reviews and ratings
- Discount and coupon codes
- Email notifications for order confirmation
- Live deployment with a public demo