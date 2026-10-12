from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of results plus the numbers a client needs to render a pager."""

    items: list[T]
    total: int
    limit: int
    offset: int
