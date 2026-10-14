from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Budget, Transaction, User
from app.seed import DEMO_EMAIL, DEMO_PASSWORD, DemoUserExists, seed_demo

TODAY = date(2026, 10, 14)


def test_seed_demo_creates_history(db):
    summary = seed_demo(db, months=6, today=TODAY)
    assert summary.first_day == date(2026, 5, 1)
    assert summary.last_day <= TODAY
    assert summary.transactions > 100
    # Budgets for September and October, five categories each.
    assert summary.budgets == 10
    assert db.scalar(select(func.count()).select_from(Budget)) == 10

    # Salary lands on the 25th, so October (seeded up to the 14th) has none yet.
    salaries = db.scalars(
        select(Transaction.occurred_on).where(Transaction.description == "Monthly salary")
    ).all()
    assert sorted(day.month for day in salaries) == [5, 6, 7, 8, 9]


def test_seed_is_deterministic(db):
    first = seed_demo(db, email="a@example.com", today=TODAY)
    second = seed_demo(db, email="b@example.com", today=TODAY)
    assert first.transactions == second.transactions

    def history(email):
        user_id = db.scalar(select(User.id).where(User.email == email))
        return db.execute(
            select(Transaction.occurred_on, Transaction.amount, Transaction.description)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.id)
        ).all()

    assert history("a@example.com") == history("b@example.com")


def test_seed_refuses_existing_user_unless_reset(db):
    seed_demo(db, months=1, today=TODAY)
    with pytest.raises(DemoUserExists):
        seed_demo(db, months=1, today=TODAY)

    summary = seed_demo(db, months=2, reset=True, today=TODAY)
    assert db.scalar(select(func.count()).select_from(User)) == 1
    count = db.scalar(select(func.count()).select_from(Transaction))
    assert count == summary.transactions


def test_seeded_account_works_through_the_api(client, engine):
    with Session(engine) as session:
        seed_demo(session, months=3)

    login = client.post(
        "/api/v1/auth/login", data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    trend = client.get("/api/v1/reports/trend?months=3", headers=headers).json()
    assert len(trend["items"]) == 3
    assert float(trend["totals"]["expense"]) > 0
    budgets = client.get("/api/v1/budgets", headers=headers).json()
    assert len(budgets["items"]) == 5
