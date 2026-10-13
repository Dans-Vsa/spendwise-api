"""Aggregations behind the /reports endpoints.

Queries only use portable SQL (no dialect-specific date functions): rows are grouped
by day in the database and rolled up into months in Python.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import money, percent
from app.core.months import days_in_month, first_day, last_day, month_range, shift_months
from app.models import Category, Transaction, TransactionType, User
from app.schemas.report import (
    CategoryBreakdown,
    CategoryTotal,
    MonthlySummary,
    MonthTotals,
    PeriodTotals,
    Trend,
)

UNCATEGORIZED = "Uncategorized"


def _in_period(user: User, start: date, end: date):
    return (
        Transaction.user_id == user.id,
        Transaction.occurred_on >= start,
        Transaction.occurred_on <= end,
    )


def category_breakdown(
    db: Session, user: User, month: date, tx_type: TransactionType = TransactionType.EXPENSE
) -> CategoryBreakdown:
    """Totals per category (largest first) for one type of transaction in `month`."""
    rows = db.execute(
        select(
            Transaction.category_id,
            Category.name,
            Category.color,
            func.sum(Transaction.amount),
            func.count(Transaction.id),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(*_in_period(user, month, last_day(month)), Transaction.type == tx_type)
        .group_by(Transaction.category_id, Category.name, Category.color)
    ).all()
    total = sum((money(row[3]) for row in rows), money(0))
    items = [
        CategoryTotal(
            category_id=category_id,
            name=name or UNCATEGORIZED,
            color=color,
            total=money(amount),
            count=count,
            share=percent(money(amount), total) or 0.0,
        )
        for category_id, name, color, amount, count in rows
    ]
    items.sort(key=lambda item: (-item.total, item.name.lower()))
    return CategoryBreakdown(month=month, type=tx_type, total=total, items=items)


def monthly_summary(db: Session, user: User, month: date) -> MonthlySummary:
    totals = dict(
        db.execute(
            select(Transaction.type, func.sum(Transaction.amount))
            .where(*_in_period(user, month, last_day(month)))
            .group_by(Transaction.type)
        ).all()
    )
    count = db.scalar(
        select(func.count(Transaction.id)).where(*_in_period(user, month, last_day(month)))
    )
    income = money(totals.get(TransactionType.INCOME))
    expense = money(totals.get(TransactionType.EXPENSE))
    net = income - expense
    expenses = category_breakdown(db, user, month, TransactionType.EXPENSE)
    return MonthlySummary(
        month=month,
        income=income,
        expense=expense,
        net=net,
        savings_rate=percent(net, income),
        transaction_count=count or 0,
        daily_average_expense=money(expense / days_in_month(month)),
        top_expense_category=expenses.items[0] if expenses.items else None,
    )


def trend(db: Session, user: User, end: date, months: int) -> Trend:
    """Income, expense and net for each of the `months` months ending with `end`."""
    start = shift_months(end, -(months - 1))
    rows = db.execute(
        select(Transaction.occurred_on, Transaction.type, func.sum(Transaction.amount))
        .where(*_in_period(user, start, last_day(end)))
        .group_by(Transaction.occurred_on, Transaction.type)
    ).all()

    by_month: dict[date, dict[TransactionType, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: money(0))
    )
    for occurred_on, tx_type, amount in rows:
        by_month[first_day(occurred_on)][tx_type] += money(amount)

    items = []
    for month in month_range(start, end):
        income = by_month[month][TransactionType.INCOME]
        expense = by_month[month][TransactionType.EXPENSE]
        items.append(MonthTotals(month=month, income=income, expense=expense, net=income - expense))

    income = sum((item.income for item in items), money(0))
    expense = sum((item.expense for item in items), money(0))
    return Trend(
        start=start,
        end=end,
        items=items,
        totals=PeriodTotals(income=income, expense=expense, net=income - expense),
        monthly_average=PeriodTotals(
            income=money(income / months),
            expense=money(expense / months),
            net=money((income - expense) / months),
        ),
    )
