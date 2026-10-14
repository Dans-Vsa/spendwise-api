"""Fill the database with a realistic demo account.

    python -m app.seed                      # demo@example.com / demo-pass1, last 6 months
    python -m app.seed --months 12 --reset  # recreate the account with a year of data

The data is generated from a fixed random seed, so every run produces the same history
(relative to today's date).
"""

import argparse
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.months import last_day, shift_months
from app.core.security import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import Budget, Category, Transaction, TransactionType, User
from app.services.categories import seed_default_categories

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-pass1"  # local demo data only

EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME

# Monthly budget limits for the most recent months.
BUDGETS = {
    "Food & Drinks": "300",
    "Groceries": "450",
    "Transport": "120",
    "Entertainment": "100",
    "Shopping": "200",
}


@dataclass
class SeedSummary:
    user_id: int
    transactions: int
    budgets: int
    first_day: date
    last_day: date


class DemoUserExists(Exception):
    pass


def _money(rng: random.Random, low: float, high: float) -> Decimal:
    return Decimal(f"{rng.uniform(low, high):.2f}")


def _month_entries(rng: random.Random, start: date, end: date) -> list[tuple]:
    """(day, type, category, amount, description) for one month, clipped to `end`."""
    days = last_day(start).day
    entries: list[tuple] = []

    def add(day: int, kind: TransactionType, category: str, amount, description: str) -> None:
        entries.append((start.replace(day=day), kind, category, Decimal(amount), description))

    def random_day() -> int:
        return rng.randint(1, days)

    # Fixed monthly income and bills.
    add(1, EXPENSE, "Housing", "950.00", "Rent")
    add(10, EXPENSE, "Bills & Utilities", _money(rng, 80, 140), "Electricity & water")
    add(12, EXPENSE, "Bills & Utilities", "39.99", "Internet")
    add(15, EXPENSE, "Entertainment", "15.49", "Streaming subscription")
    add(25, INCOME, "Salary", "3200.00", "Monthly salary")
    if rng.random() < 0.5:
        add(rng.randint(5, 20), INCOME, "Freelance", _money(rng, 200, 800), "Freelance project")

    # Variable day-to-day spending.
    for day in range(1, days + 1, 7):
        add(day, EXPENSE, "Groceries", _money(rng, 60, 120), "Weekly groceries")
    for _ in range(rng.randint(8, 14)):
        what = rng.choice(["Coffee", "Lunch", "Dinner out", "Takeaway"])
        add(random_day(), EXPENSE, "Food & Drinks", _money(rng, 6, 35), what)
    for _ in range(rng.randint(4, 8)):
        what = rng.choice(["Bus ticket", "Taxi", "Fuel"])
        add(random_day(), EXPENSE, "Transport", _money(rng, 3, 25), what)
    for _ in range(rng.randint(0, 3)):
        what = rng.choice(["Clothes", "Electronics", "Home goods"])
        add(random_day(), EXPENSE, "Shopping", _money(rng, 20, 150), what)
    if rng.random() < 0.3:
        add(random_day(), EXPENSE, "Health", _money(rng, 15, 90), "Pharmacy")

    return [entry for entry in entries if entry[0] <= end]


def seed_demo(
    db: Session,
    *,
    email: str = DEMO_EMAIL,
    password: str = DEMO_PASSWORD,
    months: int = 6,
    reset: bool = False,
    today: date | None = None,
    random_seed: int = 42,
) -> SeedSummary:
    """Create `email` with default categories, `months` of transactions and budgets."""
    today = today or date.today()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        if not reset:
            raise DemoUserExists(f"{email} already exists (use --reset to recreate it)")
        db.delete(existing)
        db.flush()

    user = User(email=email, full_name="Demo User", hashed_password=hash_password(password))
    db.add(user)
    categories = {category.name: category for category in seed_default_categories(db, user)}

    rng = random.Random(random_seed)
    current = today.replace(day=1)
    first = shift_months(current, -(months - 1))
    transactions = []
    for offset in range(months):
        month = shift_months(first, offset)
        for day, kind, category, amount, description in _month_entries(rng, month, today):
            transactions.append(
                Transaction(
                    user=user,
                    category=categories[category],
                    type=kind,
                    amount=amount,
                    occurred_on=day,
                    description=description,
                )
            )
    db.add_all(transactions)

    budgets = [
        Budget(user=user, category=categories[name], month=month, amount=Decimal(limit))
        for month in (shift_months(current, -1), current)
        if month >= first
        for name, limit in BUDGETS.items()
    ]
    db.add_all(budgets)
    db.commit()
    return SeedSummary(
        user_id=user.id,
        transactions=len(transactions),
        budgets=len(budgets),
        first_day=min(tx.occurred_on for tx in transactions),
        last_day=max(tx.occurred_on for tx in transactions),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a demo account with sample data.")
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    parser.add_argument("--months", type=int, default=6, choices=range(1, 25), metavar="1-24")
    parser.add_argument("--reset", action="store_true", help="delete and recreate the account")
    args = parser.parse_args(argv)

    init_db()
    with SessionLocal() as db:
        try:
            summary = seed_demo(
                db, email=args.email, password=args.password, months=args.months, reset=args.reset
            )
        except DemoUserExists as exc:
            print(exc)
            return 1
    print(
        f"Created {args.email} (password: {args.password}) with {summary.transactions} "
        f"transactions from {summary.first_day} to {summary.last_day} "
        f"and {summary.budgets} budgets."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
