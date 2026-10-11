import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import TransactionType

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean_name(value: str) -> str:
    value = " ".join(value.split())  # trim and collapse inner whitespace
    if not value:
        raise ValueError("name must not be blank")
    return value


def _check_color(value: str | None) -> str | None:
    if value is None:
        return None
    if not HEX_COLOR.match(value):
        raise ValueError("color must be a hex code like #4caf50")
    return value.lower()


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: TransactionType
    color: str | None = None
    icon: str | None = Field(default=None, max_length=40)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("color")
    @classmethod
    def check_color(cls, value: str | None) -> str | None:
        return _check_color(value)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    kind: TransactionType | None = None
    color: str | None = None
    icon: str | None = Field(default=None, max_length=40)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @field_validator("color")
    @classmethod
    def check_color(cls, value: str | None) -> str | None:
        return _check_color(value)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: TransactionType
    color: str | None
    icon: str | None
    created_at: datetime
