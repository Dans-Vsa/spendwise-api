from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.security import hash_password
from app.models import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, summary="Get the current user's profile")
def read_me(current_user: CurrentUser) -> User:
    return current_user


@router.patch("/me", response_model=UserRead, summary="Update profile, currency or password")
def update_me(payload: UserUpdate, current_user: CurrentUser, db: DbSession) -> User:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "password" in changes:
        current_user.hashed_password = hash_password(changes.pop("password"))
    for field, value in changes.items():
        setattr(current_user, field, value)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user
