from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.months import Month, current_month
from app.models import TransactionType
from app.schemas.report import CategoryBreakdown, MonthlySummary, Trend
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])

MonthParam = Annotated[Month | None, Query(description="YYYY-MM, defaults to the current month")]


@router.get(
    "/summary", response_model=MonthlySummary, summary="Income, expenses and net for a month"
)
def monthly_summary(
    current_user: CurrentUser, db: DbSession, month: MonthParam = None
) -> MonthlySummary:
    return reports.monthly_summary(db, current_user, month or current_month())


@router.get(
    "/categories", response_model=CategoryBreakdown, summary="Totals per category for a month"
)
def category_breakdown(
    current_user: CurrentUser,
    db: DbSession,
    month: MonthParam = None,
    type: TransactionType = TransactionType.EXPENSE,
) -> CategoryBreakdown:
    return reports.category_breakdown(db, current_user, month or current_month(), type)


@router.get("/trend", response_model=Trend, summary="Month-by-month totals over a period")
def trend(
    current_user: CurrentUser,
    db: DbSession,
    end: Annotated[Month | None, Query(description="Last month (YYYY-MM), defaults to now")] = None,
    months: Annotated[int, Query(ge=1, le=24, description="Number of months to include")] = 6,
) -> Trend:
    return reports.trend(db, current_user, end or current_month(), months)
