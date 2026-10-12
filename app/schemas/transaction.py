import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import TransactionType

# Positive, at most 2 decimal places, fits NUMERIC(12, 2).
Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


def _clean_text(value: str | None) -> str | None:
    return None if value is None else " ".join(value.split())


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class TransactionCreate(BaseModel):
    type: TransactionType
    amount: Amount
    occurred_on: date = Field(default_factory=date.today)
    category_id: int | None = None
    description: str = Field(default="", max_length=200)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return _clean_text(value) or ""

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class TransactionUpdate(BaseModel):
    type: TransactionType | None = None
    amount: Amount | None = None
    occurred_on: date | None = None
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return _clean_text(value)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: TransactionType
    # Serialized as a string ("12.50") so clients never lose precision to floats.
    amount: Decimal
    occurred_on: date
    category_id: int | None
    description: str
    note: str | None
    created_at: datetime
    updated_at: datetime


class TransactionSort(str, enum.Enum):
    NEWEST = "-occurred_on"
    OLDEST = "occurred_on"
    LARGEST = "-amount"
    SMALLEST = "amount"
    RECENTLY_ADDED = "-created_at"
    FIRST_ADDED = "created_at"


class TransactionFilters(BaseModel):
    """Query parameters accepted by `GET /transactions`."""

    model_config = ConfigDict(extra="forbid")

    type: TransactionType | None = None
    category_id: int | None = Field(default=None, description="Only this category")
    uncategorized: bool = Field(default=False, description="Only transactions without a category")
    date_from: date | None = Field(default=None, description="Inclusive start date")
    date_to: date | None = Field(default=None, description="Inclusive end date")
    min_amount: Decimal | None = Field(default=None, ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)
    q: str | None = Field(
        default=None, max_length=100, description="Case-insensitive search in description and note"
    )
    sort: TransactionSort = TransactionSort.NEWEST
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("q")
    @classmethod
    def clean_query(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def check_ranges(self) -> "TransactionFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            raise ValueError("min_amount must not exceed max_amount")
        if self.uncategorized and self.category_id is not None:
            raise ValueError("use either category_id or uncategorized, not both")
        return self
