"""Budget progress: how much of each monthly limit has been spent."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.money import money, percent
from app.core.months import last_day
from app.models import Budget, Category, Transaction, TransactionType, User
from app.schemas.budget import BudgetOverview, BudgetProgress, BudgetRead, BudgetStatus


def spent_by_category(
    db: Session, user: User, month: date, category_ids: list[int] | None = None
) -> dict[int, Decimal]:
    """Total expenses per category in `month` (categories without spending are omitted)."""
    query = (
        select(Transaction.category_id, func.sum(Transaction.amount))
        .where(
            Transaction.user_id == user.id,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.category_id.is_not(None),
            Transaction.occurred_on >= month,
            Transaction.occurred_on <= last_day(month),
        )
        .group_by(Transaction.category_id)
    )
    if category_ids is not None:
        query = query.where(Transaction.category_id.in_(category_ids))
    return {category_id: money(total) for category_id, total in db.execute(query)}


def budget_status(spent: Decimal, limit: Decimal) -> BudgetStatus:
    if spent > limit:
        return BudgetStatus.OVER
    if spent * 100 >= limit * Decimal(str(get_settings().budget_warning_percent)):
        return BudgetStatus.WARNING
    return BudgetStatus.OK


def build_progress(budget: Budget, spent: Decimal) -> BudgetProgress:
    limit = money(budget.amount)
    return BudgetProgress(
        **BudgetRead.model_validate(budget).model_dump(),
        category_name=budget.category.name,
        spent=spent,
        remaining=limit - spent,
        percent_used=percent(spent, limit) or 0.0,
        status=budget_status(spent, limit),
    )


def budget_progress(db: Session, user: User, budget: Budget) -> BudgetProgress:
    spent = spent_by_category(db, user, budget.month, [budget.category_id])
    return build_progress(budget, spent.get(budget.category_id, money(0)))


def month_overview(db: Session, user: User, month: date) -> BudgetOverview:
    """All of `user`'s budgets for `month` with spending, sorted by category name."""
    budgets = db.scalars(
        select(Budget)
        .join(Budget.category)
        .where(Budget.user_id == user.id, Budget.month == month)
        .order_by(func.lower(Category.name))
    ).all()
    spent = spent_by_category(db, user, month, [b.category_id for b in budgets])
    items = [build_progress(b, spent.get(b.category_id, money(0))) for b in budgets]
    total_budgeted = sum((item.amount for item in items), money(0))
    total_spent = sum((item.spent for item in items), money(0))
    return BudgetOverview(
        month=month,
        total_budgeted=total_budgeted,
        total_spent=total_spent,
        total_remaining=total_budgeted - total_spent,
        over_budget=sum(item.status is BudgetStatus.OVER for item in items),
        items=items,
    )
