import enum
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.months import Month, current_month
from app.schemas.transaction import Amount


class BudgetCreate(BaseModel):
    category_id: int
    month: Month = Field(default_factory=current_month, description="YYYY-MM, defaults to now")
    amount: Amount


class BudgetUpdate(BaseModel):
    amount: Amount


class BudgetCopy(BaseModel):
    """Copy every budget of one month into another (existing ones are kept)."""

    source: Month
    target: Month


class BudgetStatus(str, enum.Enum):
    OK = "ok"
    WARNING = "warning"  # at or above the warning threshold, still within the limit
    OVER = "over"


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    month: Month
    amount: Decimal
    created_at: datetime
    updated_at: datetime


class BudgetProgress(BudgetRead):
    """A budget plus how much of it has been spent so far."""

    category_name: str
    spent: Decimal
    # Negative when the budget is overspent.
    remaining: Decimal
    percent_used: float
    status: BudgetStatus


class BudgetOverview(BaseModel):
    month: Month
    total_budgeted: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    over_budget: int = Field(description="Number of overspent budgets")
    items: list[BudgetProgress]


class BudgetCopyResult(BaseModel):
    created: list[BudgetRead]
    skipped: int = Field(description="Budgets already present in the target month")
