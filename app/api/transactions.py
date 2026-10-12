from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.categories import get_owned_category
from app.api.deps import CurrentUser, DbSession
from app.models import Transaction, TransactionType, User
from app.schemas.pagination import Page
from app.schemas.transaction import (
    TransactionCreate,
    TransactionFilters,
    TransactionRead,
    TransactionUpdate,
)
from app.services.transactions import search_transactions

router = APIRouter(prefix="/transactions", tags=["transactions"])

# Required columns: an explicit null in a PATCH body means "leave unchanged".
_REQUIRED_FIELDS = ("type", "amount", "occurred_on", "description")


def get_owned_transaction(db: DbSession, user: User, transaction_id: int) -> Transaction:
    """Fetch a transaction that belongs to `user`; other users' transactions look like 404s."""
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user.id)
    )
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


def check_category(
    db: DbSession, user: User, category_id: int | None, tx_type: TransactionType
) -> None:
    """The category must be the user's own and of the same kind as the transaction."""
    if category_id is None:
        return
    try:
        category = get_owned_category(db, user, category_id)
    except HTTPException as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Category not found"
        ) from exc
    if category.kind != tx_type:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Category '{category.name}' is for {category.kind.value}, "
            f"not {tx_type.value} transactions",
        )


@router.get("", response_model=Page[TransactionRead], summary="List, filter and page transactions")
def list_transactions(
    current_user: CurrentUser,
    db: DbSession,
    filters: Annotated[TransactionFilters, Query()],
) -> dict:
    items, total = search_transactions(db, current_user, filters)
    return {"items": items, "total": total, "limit": filters.limit, "offset": filters.offset}


@router.post(
    "",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an income or expense",
)
def create_transaction(
    payload: TransactionCreate, current_user: CurrentUser, db: DbSession
) -> Transaction:
    check_category(db, current_user, payload.category_id, payload.type)
    transaction = Transaction(user_id=current_user.id, **payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("/{transaction_id}", response_model=TransactionRead, summary="Get one transaction")
def read_transaction(transaction_id: int, current_user: CurrentUser, db: DbSession) -> Transaction:
    return get_owned_transaction(db, current_user, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionRead, summary="Edit a transaction")
def update_transaction(
    transaction_id: int, payload: TransactionUpdate, current_user: CurrentUser, db: DbSession
) -> Transaction:
    transaction = get_owned_transaction(db, current_user, transaction_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in _REQUIRED_FIELDS:
        if changes.get(field, ...) is None:
            changes.pop(field)

    # Re-validate the category whenever the category or the type changes.
    if "category_id" in changes or "type" in changes:
        check_category(
            db,
            current_user,
            changes.get("category_id", transaction.category_id),
            changes.get("type", transaction.type),
        )

    for field, value in changes.items():
        setattr(transaction, field, value)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete(
    "/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a transaction"
)
def delete_transaction(transaction_id: int, current_user: CurrentUser, db: DbSession) -> Response:
    transaction = get_owned_transaction(db, current_user, transaction_id)
    db.delete(transaction)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
