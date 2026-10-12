"""Query building for the transactions list endpoint."""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Transaction, User
from app.schemas.transaction import TransactionFilters, TransactionSort

_SORT_COLUMNS = {
    TransactionSort.NEWEST: Transaction.occurred_on.desc(),
    TransactionSort.OLDEST: Transaction.occurred_on.asc(),
    TransactionSort.LARGEST: Transaction.amount.desc(),
    TransactionSort.SMALLEST: Transaction.amount.asc(),
    TransactionSort.RECENTLY_ADDED: Transaction.created_at.desc(),
    TransactionSort.FIRST_ADDED: Transaction.created_at.asc(),
}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filtered_query(user: User, filters: TransactionFilters) -> Select[tuple[Transaction]]:
    """Return a SELECT for `user`'s transactions matching `filters` (unsorted, unpaginated)."""
    query = select(Transaction).where(Transaction.user_id == user.id)
    if filters.type is not None:
        query = query.where(Transaction.type == filters.type)
    if filters.category_id is not None:
        query = query.where(Transaction.category_id == filters.category_id)
    if filters.uncategorized:
        query = query.where(Transaction.category_id.is_(None))
    if filters.date_from is not None:
        query = query.where(Transaction.occurred_on >= filters.date_from)
    if filters.date_to is not None:
        query = query.where(Transaction.occurred_on <= filters.date_to)
    if filters.min_amount is not None:
        query = query.where(Transaction.amount >= filters.min_amount)
    if filters.max_amount is not None:
        query = query.where(Transaction.amount <= filters.max_amount)
    if filters.q:
        pattern = f"%{_escape_like(filters.q)}%"
        query = query.where(
            or_(
                Transaction.description.ilike(pattern, escape="\\"),
                Transaction.note.ilike(pattern, escape="\\"),
            )
        )
    return query


def search_transactions(
    db: Session, user: User, filters: TransactionFilters
) -> tuple[list[Transaction], int]:
    """Return one page of matching transactions and the total match count."""
    query = filtered_query(user, filters)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    # id as a tie-breaker keeps the order stable across pages.
    descending = filters.sort.value.startswith("-")
    tie_breaker = Transaction.id.desc() if descending else Transaction.id.asc()
    page = db.scalars(
        query.order_by(_SORT_COLUMNS[filters.sort], tie_breaker)
        .limit(filters.limit)
        .offset(filters.offset)
    )
    return list(page), total
