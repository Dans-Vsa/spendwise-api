# SpendWise API

A REST API for tracking personal finances — income, expenses, categories, monthly budgets and spending reports. Built with **FastAPI** and **SQLite**, designed to be the backend for a web or mobile budgeting app.

> Status: early development (milestone 5 of 7 — transactions).

## Features

- [x] Project scaffold with FastAPI, typed settings and health check endpoint
- [x] Interactive API docs (Swagger UI at `/docs`, ReDoc at `/redoc`)
- [x] Automated tests with pytest
- [x] SQLite database layer (SQLAlchemy 2.0) with users, categories and transactions
- [x] User registration and JWT authentication (bcrypt password hashing, `/users/me` profile)
- [x] Category management (CRUD, per-user ownership, 14 default categories seeded on signup)
- [x] Transaction CRUD (income / expense) with validation, filtering, search, sorting and pagination
- [ ] Monthly budgets per category with overspend alerts
- [ ] Reports: monthly summary, category breakdown, trends
- [ ] CSV import / export, demo data script
- [ ] Docker image and GitHub Actions CI

## Tech Stack

| Layer      | Tool                              |
|------------|-----------------------------------|
| Language   | Python 3.11+                      |
| Framework  | FastAPI                           |
| Server     | Uvicorn                           |
| Config     | pydantic-settings (`.env`)        |
| Database   | SQLite + SQLAlchemy 2.0           |
| Auth       | OAuth2 password flow, JWT (PyJWT), bcrypt |
| Testing    | pytest + httpx `TestClient`       |

## Getting Started

```bash
git clone https://github.com/Dans-Vsa/spendwise-api.git
cd spendwise-api

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env   # optional
```

Create the database tables (also done automatically when the server starts):

```bash
python -m app.db.init_db
```

Run the development server:

```bash
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/docs> for the interactive API docs.

Run the tests:

```bash
pytest
```

## Configuration

All settings are read from environment variables with the `SPENDWISE_` prefix (or from a `.env` file):

| Variable                 | Default                     | Description                  |
|--------------------------|-----------------------------|------------------------------|
| `SPENDWISE_ENVIRONMENT`  | `development`               | Environment name             |
| `SPENDWISE_DEBUG`        | `false`                     | FastAPI debug mode           |
| `SPENDWISE_DATABASE_URL` | `sqlite:///./spendwise.db`  | SQLAlchemy database URL      |
| `SPENDWISE_JWT_SECRET_KEY` | dev-only placeholder      | Secret used to sign JWTs — **set this in production** |
| `SPENDWISE_ACCESS_TOKEN_EXPIRE_MINUTES` | `60`         | Access token lifetime        |

## API Endpoints

| Method | Path                     | Auth | Description                                   |
|--------|--------------------------|------|-----------------------------------------------|
| GET    | `/api/v1/health`         | —    | Service + database health check               |
| POST   | `/api/v1/auth/register`  | —    | Create an account (JSON: `email`, `password`, `full_name`, `currency`) |
| POST   | `/api/v1/auth/login`     | —    | OAuth2 password form (`username` = email) → JWT access token |
| GET    | `/api/v1/users/me`       | JWT  | Current user's profile                        |
| PATCH  | `/api/v1/users/me`       | JWT  | Update name, currency or password             |
| GET    | `/api/v1/categories`     | JWT  | List your categories (optional `?kind=income\|expense`) |
| POST   | `/api/v1/categories`     | JWT  | Create a category (`name`, `kind`, `color`, `icon`) |
| GET    | `/api/v1/categories/{id}`| JWT  | Get one category                              |
| PATCH  | `/api/v1/categories/{id}`| JWT  | Rename / recolor / change kind                |
| DELETE | `/api/v1/categories/{id}`| JWT  | Delete a category (its transactions become uncategorized) |
| GET    | `/api/v1/transactions`   | JWT  | List transactions — filter, search, sort, paginate (see below) |
| POST   | `/api/v1/transactions`   | JWT  | Record an income or expense                   |
| GET    | `/api/v1/transactions/{id}` | JWT | Get one transaction                          |
| PATCH  | `/api/v1/transactions/{id}` | JWT | Edit amount, date, category, description, note |
| DELETE | `/api/v1/transactions/{id}` | JWT | Delete a transaction                         |

### Authentication example

```bash
# 1. Register
curl -X POST http://127.0.0.1:8000/api/v1/auth/register   -H "Content-Type: application/json"   -d '{"email": "demo@example.com", "password": "demo-pass1", "full_name": "Demo"}'

# 2. Log in (form data, OAuth2 password flow) -> {"access_token": "...", "token_type": "bearer"}
curl -X POST http://127.0.0.1:8000/api/v1/auth/login   -d "username=demo@example.com&password=demo-pass1"

# 3. Call protected endpoints with the token
curl http://127.0.0.1:8000/api/v1/users/me -H "Authorization: Bearer <access_token>"
```

In Swagger UI (`/docs`) click **Authorize** and enter your email + password to try protected endpoints.

Password rules: 8–72 bytes, must not be only letters or only digits. Emails are stored lowercase, currency as an uppercase 3-letter code.

### Categories

Every new account starts with 14 default categories (e.g. *Salary*, *Freelance*, *Food & Drinks*, *Transport*, *Bills & Utilities*) so the app is usable immediately.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/categories -H "Authorization: Bearer <access_token>" \n  -H "Content-Type: application/json" -d '{"name": "Coffee", "kind": "expense", "color": "#6d4c41", "icon": "cup"}'
```

Rules:

- Names are trimmed and must be unique per user and kind (case-insensitive) → `409 Conflict` otherwise.
- `color` must be a hex code like `#4caf50` (stored lowercase).
- Other users' categories always return `404 Not Found`.
- A category's `kind` cannot change once it has transactions (`409`).

### Transactions

```bash
curl -X POST http://127.0.0.1:8000/api/v1/transactions -H "Authorization: Bearer <access_token>"   -H "Content-Type: application/json"   -d '{"type": "expense", "amount": "12.50", "occurred_on": "2026-10-12", "category_id": 5, "description": "Lunch"}'
```

Rules:

- `amount` must be positive with at most 2 decimal places (max `9999999999.99`). Responses return it as a string (`"12.50"`) so no precision is lost to floats.
- `occurred_on` defaults to today; `category_id` is optional (uncategorized).
- The category must belong to you **and** match the transaction type (an expense can't go in *Salary*) → `422` otherwise. Changing `type` via `PATCH` re-checks this.
- In `PATCH`, `null` clears optional fields (`category_id`, `note`) and is ignored for required ones.
- Other users' transactions always return `404 Not Found`.

Listing supports these query parameters (all optional, combinable):

| Parameter                   | Example                     | Meaning                                         |
|-----------------------------|-----------------------------|-------------------------------------------------|
| `type`                      | `expense`                   | Only income or only expenses                    |
| `category_id` / `uncategorized` | `5` / `true`            | One category, or only uncategorized rows        |
| `date_from`, `date_to`      | `2026-10-01`, `2026-10-31`  | Inclusive date range                            |
| `min_amount`, `max_amount`  | `10`, `100`                 | Inclusive amount range                          |
| `q`                         | `coffee`                    | Case-insensitive search in description and note |
| `sort`                      | `-amount`                   | `occurred_on`, `amount`, `created_at`; prefix `-` for descending (default `-occurred_on`) |
| `limit`, `offset`           | `20`, `40`                  | Page size (1–100, default 20) and offset        |

```bash
curl "http://127.0.0.1:8000/api/v1/transactions?type=expense&date_from=2026-10-01&date_to=2026-10-31&sort=-amount&limit=10"   -H "Authorization: Bearer <access_token>"
# -> {"items": [...], "total": 42, "limit": 10, "offset": 0}
```

Unknown parameters and inconsistent ranges (e.g. `date_from` after `date_to`) are rejected with `422`.

## Data Model

| Table          | Key columns                                                                 |
|----------------|-----------------------------------------------------------------------------|
| `users`        | `email` (unique), `full_name`, `hashed_password`, `currency`, `is_active`    |
| `categories`   | `user_id`, `name`, `kind` (`income`/`expense`), `color`, `icon` — unique per user + name + kind |
| `transactions` | `user_id`, `category_id` (nullable), `type`, `amount` (`NUMERIC(12,2)`, > 0), `description`, `note`, `occurred_on` |

- Every table has `created_at` / `updated_at` timestamps (UTC).
- Deleting a user cascades to their categories and transactions.
- Deleting a category keeps its transactions (they become uncategorized).
- Money is stored as exact decimals, never floats. SQLite foreign keys are enforced.

## Project Structure

```
spendwise-api/
├── app/
│   ├── __init__.py       # package version
│   ├── main.py           # FastAPI app factory
│   ├── config.py         # environment-based settings
│   ├── api/
│   │   ├── deps.py       # shared dependencies (DB session, current user)
│   │   ├── health.py     # health check route
│   │   ├── auth.py       # register + login (seeds default categories)
│   │   ├── categories.py # categories CRUD
│   │   ├── transactions.py # transactions CRUD + list/filter endpoint
│   │   └── users.py      # /users/me
│   ├── core/
│   │   └── security.py   # bcrypt hashing + JWT helpers
│   ├── schemas/
│   │   ├── user.py       # user/auth request + response models
│   │   ├── category.py   # category request + response models
│   │   ├── transaction.py # transaction models + list filters/sort options
│   │   └── pagination.py # generic Page[T] response
│   ├── services/
│   │   ├── categories.py # default categories + seeding
│   │   └── transactions.py # filter / sort / paginate query builder
│   ├── db/
│   │   ├── base.py       # declarative base + timestamp mixin
│   │   ├── session.py    # engine, session factory, get_db dependency
│   │   └── init_db.py    # table creation (python -m app.db.init_db)
│   └── models/
│       ├── user.py
│       ├── category.py
│       └── transaction.py
├── tests/
│   ├── conftest.py       # isolated in-memory DB per test + auth fixtures
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_categories.py
│   ├── test_transactions.py        # CRUD, validation, ownership
│   ├── test_transaction_queries.py # filters, search, sorting, pagination
│   └── test_models.py
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .env.example
└── LICENSE
```

## License

[MIT](LICENSE) © Dans-Vsa
