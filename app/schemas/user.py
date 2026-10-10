from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES


def _check_password(value: str) -> str:
    if len(value.encode()) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password must be at most {BCRYPT_MAX_BYTES} bytes")
    if value.isdigit() or value.isalpha():
        raise ValueError("password must contain letters and at least one number or symbol")
    return value


def _normalize_currency(value: str) -> str:
    value = value.upper()
    if not value.isalpha():
        raise ValueError("currency must be a 3-letter ISO 4217 code")
    return value


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=BCRYPT_MAX_BYTES)
    full_name: str | None = Field(default=None, max_length=120)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return _check_password(value)

    @field_validator("currency")
    @classmethod
    def check_currency(cls, value: str) -> str:
        return _normalize_currency(value)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    password: str | None = Field(default=None, min_length=8, max_length=BCRYPT_MAX_BYTES)

    @field_validator("currency")
    @classmethod
    def check_currency(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_currency(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str | None) -> str | None:
        return None if value is None else _check_password(value)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None
    currency: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
