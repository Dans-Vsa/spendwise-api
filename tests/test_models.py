from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import Category, Transaction, TransactionType, User


def make_user(db, email="ana@example.com") -> User:
    user = User(email=email, full_name="Ana", hashed_password="not-a-real-hash")
    db.add(user)
    db.commit()
    return user


def test_tables_are_created(engine):
    assert set(inspect(engine).get_table_names()) >= {"users", "categories", "transactions"}


def test_user_defaults(db):
    user = make_user(db)
    assert user.id is not None
    assert user.currency == "USD"
    assert user.is_active is True
    assert user.created_at is not None


def test_user_email_is_unique(db):
    make_user(db)
    db.add(User(email="ana@example.com", hashed_password="x"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_transaction_with_category_roundtrip(db):
    user = make_user(db)
    food = Category(user=user, name="Food", kind=TransactionType.EXPENSE, color="#ff7043")
    db.add(
        Transaction(
            user=user,
            category=food,
            type=TransactionType.EXPENSE,
            amount=Decimal("12.50"),
            description="Lunch",
            occurred_on=date(2026, 10, 9),
        )
    )
    db.commit()

    tx = db.scalars(select(Transaction)).one()
    assert tx.amount == Decimal("12.50")
    assert tx.type is TransactionType.EXPENSE
    assert tx.category.name == "Food"
    assert user.transactions == [tx]


def test_amount_must_be_positive(db):
    user = make_user(db)
    db.add(
        Transaction(
            user=user, type=TransactionType.INCOME, amount=Decimal("0"), occurred_on=date.today()
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_category_name_unique_per_user_and_kind(db):
    user = make_user(db)
    db.add(Category(user=user, name="Salary", kind=TransactionType.INCOME))
    db.commit()
    db.add(Category(user=user, name="Salary", kind=TransactionType.INCOME))
    with pytest.raises(IntegrityError):
        db.commit()


def test_same_category_name_allowed_for_other_user(db):
    ana, budi = make_user(db), make_user(db, "budi@example.com")
    db.add_all(
        [
            Category(user=ana, name="Food", kind=TransactionType.EXPENSE),
            Category(user=budi, name="Food", kind=TransactionType.EXPENSE),
        ]
    )
    db.commit()
    assert len(db.scalars(select(Category)).all()) == 2


def test_deleting_user_cascades(db):
    user = make_user(db)
    cat = Category(user=user, name="Rent", kind=TransactionType.EXPENSE)
    db.add(
        Transaction(
            user=user, category=cat, type=TransactionType.EXPENSE,
            amount=Decimal("500"), occurred_on=date(2026, 10, 1),
        )
    )
    db.commit()

    db.delete(user)
    db.commit()
    assert db.scalars(select(Category)).all() == []
    assert db.scalars(select(Transaction)).all() == []


def test_deleting_category_keeps_transactions(db):
    user = make_user(db)
    cat = Category(user=user, name="Misc", kind=TransactionType.EXPENSE)
    db.add(
        Transaction(
            user=user, category=cat, type=TransactionType.EXPENSE,
            amount=Decimal("3.20"), occurred_on=date(2026, 10, 2),
        )
    )
    db.commit()

    db.delete(cat)
    db.commit()
    db.expire_all()
    tx = db.scalars(select(Transaction)).one()
    assert tx.category_id is None
