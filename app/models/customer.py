"""Customer model for MediLab AI."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import TimestampMixin


class Customer(TimestampMixin, db.Model):
    """Patient/customer booking diagnostic laboratory services."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Locked decision: phone is unique to support unambiguous deterministic customer resolution
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Customer id={self.id} name='{self.name}' phone='{self.phone}'>"
