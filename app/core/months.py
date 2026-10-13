"""Calendar-month helpers and the `Month` ("YYYY-MM") type used by budgets and reports."""

import calendar
import re
from datetime import date
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")


def first_day(value: date) -> date:
    return value.replace(day=1)


def current_month() -> date:
    return first_day(date.today())


def last_day(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def days_in_month(month: date) -> int:
    return calendar.monthrange(month.year, month.month)[1]


def shift_months(month: date, count: int) -> date:
    """Move `count` months forward (or backward if negative); the result is a first day."""
    index = month.year * 12 + (month.month - 1) + count
    return date(index // 12, index % 12 + 1, 1)


def month_range(start: date, end: date) -> list[date]:
    """Every month from `start` to `end`, inclusive."""
    months, current = [], first_day(start)
    while current <= end:
        months.append(current)
        current = shift_months(current, 1)
    return months


def format_month(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


def parse_month(value: Any) -> date:
    """Accept "YYYY-MM" (or a date) and return the first day of that month."""
    if isinstance(value, date):
        return first_day(value)
    if isinstance(value, str):
        match = _MONTH_PATTERN.match(value.strip())
        if match:
            year, month = int(match[1]), int(match[2])
            if 1 <= month <= 12 and year >= 1:
                return date(year, month, 1)
    raise ValueError("month must be in YYYY-MM format, e.g. 2026-10")


Month = Annotated[
    date,
    BeforeValidator(parse_month),
    PlainSerializer(format_month, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": r"^\d{4}-\d{2}$", "examples": ["2026-10"]}),
]
