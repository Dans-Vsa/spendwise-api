# SpendWise API

A REST API for tracking personal finances — income, expenses, categories, monthly budgets and spending reports. Built with **FastAPI** and **SQLite**, designed to be the backend for a web or mobile budgeting app.

> Status: early development (milestone 1 of 12 — project scaffold).

## Features

- [x] Project scaffold with FastAPI, typed settings and health check endpoint
- [x] Interactive API docs (Swagger UI at `/docs`, ReDoc at `/redoc`)
- [x] Automated tests with pytest
- [ ] SQLite database layer (SQLAlchemy 2.0) with users, categories and transactions
- [ ] User registration and JWT authentication
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
| Database   | SQLite + SQLAlchemy 2.0 (planned) |
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

## API Endpoints

| Method | Path              | Description          |
|--------|-------------------|----------------------|
| GET    | `/api/v1/health`  | Service health check |

## Project Structure

```
spendwise-api/
├── app/
│   ├── __init__.py       # package version
│   ├── main.py           # FastAPI app factory
│   ├── config.py         # environment-based settings
│   └── api/
│       └── health.py     # health check route
├── tests/
│   └── test_health.py
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .env.example
└── LICENSE
```

## License

[MIT](LICENSE) © Dans-Vsa
