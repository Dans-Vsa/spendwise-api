from datetime import date
from decimal import Decimal

import pytest

from app.core.money import money, percent
from app.core.months import (
    days_in_month,
    format_month,
    last_day,
    month_range,
    parse_month,
    shift_months,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10", date(2026, 10, 1)),
        (" 2024-02 ", date(2024, 2, 1)),
        (date(2026, 3, 17), date(2026, 3, 1)),
    ],
)
def test_parse_month(value, expected):
    assert parse_month(value) == expected


@pytest.mark.parametrize(
    "value", ["2026-13", "2026-00", "2026-1", "26-10", "2026/10", "", None, 202610]
)
def test_parse_month_rejects_bad_input(value):
    with pytest.raises(ValueError):
        parse_month(value)


def test_format_month():
    assert format_month(date(2026, 1, 1)) == "2026-01"


def test_last_day_handles_leap_years():
    assert last_day(date(2024, 2, 1)) == date(2024, 2, 29)
    assert last_day(date(2026, 2, 1)) == date(2026, 2, 28)
    assert days_in_month(date(2026, 12, 1)) == 31


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, date(2027, 1, 1)),
        (-1, date(2026, 11, 1)),
        (-12, date(2025, 12, 1)),
        (0, date(2026, 12, 1)),
    ],
)
def test_shift_months_crosses_years(count, expected):
    assert shift_months(date(2026, 12, 1), count) == expected


def test_month_range_is_inclusive():
    assert month_range(date(2026, 11, 1), date(2027, 1, 1)) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]


def test_money_and_percent():
    assert money(None) == Decimal("0.00")
    assert money(0.1 + 0.2) == Decimal("0.30")
    assert money("2.345") == Decimal("2.35")
    assert percent(Decimal("1"), Decimal("3")) == 33.3
    assert percent(Decimal("5"), Decimal("0")) is None
