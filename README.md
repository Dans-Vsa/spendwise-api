# SpendWise API

A REST API for tracking personal finances — income, expenses, categories, monthly budgets and spending reports. Built with **FastAPI** and **SQLite**, designed to be the backend for a web or mobile budgeting app.

> Status: early development (milestone 3 of 12 — user accounts and JWT authentication).

## Features

- [x] Project scaffold with FastAPI, typed settings and health check endpoint
- [x] Interactive API docs (Swagger UI at `/docs`, ReDoc at `/redoc`)
- [x] Automated tests with pytest
- [x] SQLite database layer (SQLAlchemy 2.0) with users, categories and transactions
- [x] User registration and JWT authentication (bcrypt password hashing, `/users/me` profile)
- [ ] Category management (with default categories for new users)
- [ ] Transaction CRUD (income / expense)
- [ ] Filtering, sorting and pagination of transactions
- [ ] Monthly budgets per category with overspend alerts
- [ ] Reports: monthly summary, category breakdown, trends
- [ ] CSV import / export
- [ ] Recurring transactions
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
│   │   ├── auth.py       # register + login
│   │   └── users.py      # /users/me
│   ├── core/
│   │   └── security.py   # bcrypt hashing + JWT helpers
│   ├── schemas/
│   │   └── user.py       # request/response models
│   ├── db/
│   │   ├── base.py       # declarative base + timestamp mixin
│   │   ├── session.py    # engine, session factory, get_db dependency
│   │   └── init_db.py    # table creation (python -m app.db.init_db)
│   └── models/
│       ├── user.py
│       ├── category.py
│       └── transaction.py
├── tests/
│   ├── conftest.py       # isolated in-memory DB per test
│   ├── test_health.py
│   ├── test_auth.py
│   └── test_models.py
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .env.example
└── LICENSE
```

## License

[MIT](LICENSE) © Dans-Vsa
