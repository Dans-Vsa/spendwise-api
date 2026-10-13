"""Exact money arithmetic helpers."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value: Decimal | int | float | str | None) -> Decimal:
    """Normalize a (possibly NULL) SQL sum to a 2-decimal Decimal."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def percent(part: Decimal, whole: Decimal) -> float | None:
    """`part` as a percentage of `whole`, rounded to 1 decimal; None when `whole` is zero."""
    if not whole:
        return None
    return float((part * 100 / whole).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
