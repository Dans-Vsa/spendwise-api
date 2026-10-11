from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Category, Transaction, TransactionType, User
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


def get_owned_category(db: DbSession, user: User, category_id: int) -> Category:
    """Fetch a category that belongs to `user`; other users' categories look like 404s."""
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user.id)
    )
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


def ensure_name_available(
    db: DbSession, user: User, name: str, kind: TransactionType, exclude_id: int | None = None
) -> None:
    query = select(Category.id).where(
        Category.user_id == user.id,
        Category.kind == kind,
        func.lower(Category.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"An {kind.value} category named '{name}' already exists",
        )


@router.get("", response_model=list[CategoryRead], summary="List your categories")
def list_categories(
    current_user: CurrentUser, db: DbSession, kind: TransactionType | None = None
) -> list[Category]:
    query = select(Category).where(Category.user_id == current_user.id)
    if kind is not None:
        query = query.where(Category.kind == kind)
    return list(db.scalars(query.order_by(Category.kind, func.lower(Category.name))))


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
def create_category(payload: CategoryCreate, current_user: CurrentUser, db: DbSession) -> Category:
    ensure_name_available(db, current_user, payload.name, payload.kind)
    category = Category(user_id=current_user.id, **payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/{category_id}", response_model=CategoryRead, summary="Get one category")
def read_category(category_id: int, current_user: CurrentUser, db: DbSession) -> Category:
    return get_owned_category(db, current_user, category_id)


@router.patch("/{category_id}", response_model=CategoryRead, summary="Rename or restyle a category")
def update_category(
    category_id: int, payload: CategoryUpdate, current_user: CurrentUser, db: DbSession
) -> Category:
    category = get_owned_category(db, current_user, category_id)
    changes = payload.model_dump(exclude_unset=True)
    # name/kind are required columns, so an explicit null is treated as "no change".
    for field in ("name", "kind"):
        if changes.get(field, ...) is None:
            changes.pop(field)

    new_kind = changes.get("kind", category.kind)
    if new_kind != category.kind:
        in_use = db.scalar(select(Transaction.id).where(Transaction.category_id == category.id))
        if in_use is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Cannot change the kind of a category that already has transactions",
            )
    if "name" in changes or "kind" in changes:
        ensure_name_available(
            db, current_user, changes.get("name", category.name), new_kind, exclude_id=category.id
        )

    for field, value in changes.items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category (its transactions become uncategorized)",
)
def delete_category(category_id: int, current_user: CurrentUser, db: DbSession) -> Response:
    category = get_owned_category(db, current_user, category_id)
    db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
