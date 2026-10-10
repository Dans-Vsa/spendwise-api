from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import DbSession
from app.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
def register(payload: UserCreate, db: DbSession) -> User:
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email is already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        currency=payload.currency,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token, summary="Log in and get a JWT access token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    """OAuth2 password flow: send `username` (your email) and `password` as form data."""
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Inactive user")
    settings = get_settings()
    return Token(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )
