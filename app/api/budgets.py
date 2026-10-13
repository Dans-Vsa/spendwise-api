from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.categories import get_owned_category
from app.api.deps import CurrentUser, DbSession
from app.core.months import Month, current_month, format_month
from app.models import Budget, TransactionType, User
from app.schemas.budget import (
    BudgetCopy,
    BudgetCopyResult,
    BudgetCreate,
    BudgetOverview,
    BudgetProgress,
    BudgetUpdate,
)
from app.services.budgets import budget_progress, month_overview

router = APIRouter(prefix="/budgets", tags=["budgets"])


def get_owned_budget(db: DbSession, user: User, budget_id: int) -> Budget:
    """Fetch a budget that belongs to `user`; other users' budgets look like 404s."""
    budget = db.scalar(select(Budget).where(Budget.id == budget_id, Budget.user_id == user.id))
    if budget is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return budget


def check_budget_category(db: DbSession, user: User, category_id: int) -> None:
    """Budgets can only be set on the user's own expense categories."""
    try:
        category = get_owned_category(db, user, category_id)
    except HTTPException as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Category not found"
        ) from exc
    if category.kind != TransactionType.EXPENSE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Budgets need an expense category; '{category.name}' is an income category",
        )


@router.get("", response_model=BudgetOverview, summary="Budgets for a month with spending status")
def list_budgets(
    current_user: CurrentUser,
    db: DbSession,
    month: Annotated[
        Month | None, Query(description="YYYY-MM, defaults to the current month")
    ] = None,
) -> BudgetOverview:
    return month_overview(db, current_user, month or current_month())


@router.post(
    "",
    response_model=BudgetProgress,
    status_code=status.HTTP_201_CREATED,
    summary="Set a monthly limit for an expense category",
)
def create_budget(
    payload: BudgetCreate, current_user: CurrentUser, db: DbSession
) -> BudgetProgress:
    check_budget_category(db, current_user, payload.category_id)
    duplicate = db.scalar(
        select(Budget.id).where(
            Budget.user_id == current_user.id,
            Budget.category_id == payload.category_id,
            Budget.month == payload.month,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"This category already has a budget for {format_month(payload.month)}",
        )
    budget = Budget(user_id=current_user.id, **payload.model_dump())
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget_progress(db, current_user, budget)


@router.post(
    "/copy",
    response_model=BudgetCopyResult,
    status_code=status.HTTP_201_CREATED,
    summary="Copy one month's budgets into another month",
)
def copy_budgets(payload: BudgetCopy, current_user: CurrentUser, db: DbSession) -> dict:
    if payload.source == payload.target:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="source and target must differ"
        )

    def budgets_in(month) -> list[Budget]:
        return list(
            db.scalars(
                select(Budget).where(Budget.user_id == current_user.id, Budget.month == month)
            )
        )

    existing = {b.category_id for b in budgets_in(payload.target)}
    source = budgets_in(payload.source)
    created = [
        Budget(
            user_id=current_user.id,
            category_id=b.category_id,
            month=payload.target,
            amount=b.amount,
        )
        for b in source
        if b.category_id not in existing
    ]
    db.add_all(created)
    db.commit()
    for budget in created:
        db.refresh(budget)
    return {"created": created, "skipped": len(source) - len(created)}


@router.get(
    "/{budget_id}", response_model=BudgetProgress, summary="Get one budget and its progress"
)
def read_budget(budget_id: int, current_user: CurrentUser, db: DbSession) -> BudgetProgress:
    return budget_progress(db, current_user, get_owned_budget(db, current_user, budget_id))


@router.patch("/{budget_id}", response_model=BudgetProgress, summary="Change a budget's limit")
def update_budget(
    budget_id: int, payload: BudgetUpdate, current_user: CurrentUser, db: DbSession
) -> BudgetProgress:
    budget = get_owned_budget(db, current_user, budget_id)
    budget.amount = payload.amount
    db.commit()
    db.refresh(budget)
    return budget_progress(db, current_user, budget)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a budget")
def delete_budget(budget_id: int, current_user: CurrentUser, db: DbSession) -> Response:
    budget = get_owned_budget(db, current_user, budget_id)
    db.delete(budget)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
