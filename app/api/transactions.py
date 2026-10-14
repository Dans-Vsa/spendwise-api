from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.categories import get_owned_category
from app.api.deps import CurrentUser, DbSession
from app.core.errors import ErrorResponse
from app.models import Transaction, TransactionType, User
from app.schemas.pagination import Page
from app.schemas.transaction import (
    TransactionCreate,
    TransactionFilters,
    TransactionImportResult,
    TransactionQuery,
    TransactionRead,
    TransactionUpdate,
)
from app.services.csv_io import CSVFormatError, export_transactions, import_transactions
from app.services.transactions import search_transactions

router = APIRouter(prefix="/transactions", tags=["transactions"])

MAX_IMPORT_BYTES = 1024 * 1024  # 1 MiB

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


@router.get(
    "/export",
    summary="Download matching transactions as CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV file"}},
)
def export_csv(
    current_user: CurrentUser,
    db: DbSession,
    filters: Annotated[TransactionQuery, Query()],
) -> Response:
    """Accepts the same filters and sort as the list endpoint, without pagination."""
    return Response(
        content=export_transactions(db, current_user, filters),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="transactions.csv"'},
    )


@router.post(
    "/import",
    response_model=TransactionImportResult,
    summary="Import transactions from CSV",
    responses={
        413: {"model": ErrorResponse, "description": "File larger than 1 MiB"},
        422: {"model": ErrorResponse, "description": "Invalid file or rows (nothing imported)"},
    },
)
def import_csv(
    current_user: CurrentUser,
    db: DbSession,
    file: Annotated[
        UploadFile,
        File(description="CSV with columns date,type,amount[,category,description,note]"),
    ],
    create_categories: Annotated[
        bool, Query(description="Create categories that don't exist yet instead of failing")
    ] = False,
    dry_run: Annotated[bool, Query(description="Validate only, don't save anything")] = False,
) -> TransactionImportResult:
    """All-or-nothing: if any row is invalid, nothing is imported and every problem is listed
    in `error.fields` (e.g. `row 3.amount`)."""
    # Sync route (runs in the threadpool), so read the spooled file directly.
    content = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, detail="CSV file is larger than 1 MiB"
        )
    try:
        result = import_transactions(
            db, current_user, content, create_categories=create_categories, dry_run=dry_run
        )
    except CSVFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    if result.errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": f"Import failed: {len(result.errors)} problem(s), nothing was imported",
                "fields": result.errors,
            },
        )
    if not dry_run:
        db.commit()
    return TransactionImportResult(
        imported=result.imported, dry_run=dry_run, created_categories=result.created_categories
    )


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
