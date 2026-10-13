from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.months import Month
from app.models import TransactionType


class CategoryTotal(BaseModel):
    category_id: int | None = Field(description="null for uncategorized transactions")
    name: str
    color: str | None
    total: Decimal
    count: int
    share: float = Field(description="Percentage of the period's total for this type")


class MonthlySummary(BaseModel):
    month: Month
    income: Decimal
    expense: Decimal
    net: Decimal
    savings_rate: float | None = Field(
        description="Net as a percentage of income; null if there is no income"
    )
    transaction_count: int
    daily_average_expense: Decimal
    top_expense_category: CategoryTotal | None


class CategoryBreakdown(BaseModel):
    month: Month
    type: TransactionType
    total: Decimal
    items: list[CategoryTotal]


class MonthTotals(BaseModel):
    month: Month
    income: Decimal
    expense: Decimal
    net: Decimal


class PeriodTotals(BaseModel):
    income: Decimal
    expense: Decimal
    net: Decimal


class Trend(BaseModel):
    start: Month
    end: Month
    items: list[MonthTotals]
    totals: PeriodTotals
    monthly_average: PeriodTotals
