from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.transaction import TransactionType

if TYPE_CHECKING:
    from app.models.transaction import Transaction
    from app.models.user import User


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", "kind", name="user_name_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, native_enum=False, length=10)
    )
    color: Mapped[str | None] = mapped_column(String(7))  # hex, e.g. "#4caf50"
    icon: Mapped[str | None] = mapped_column(String(40))

    user: Mapped["User"] = relationship(back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} kind={self.kind.value}>"
