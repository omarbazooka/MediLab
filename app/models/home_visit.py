"""HomeVisit model for home sample collection requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.booking import Booking


class HomeVisit(TimestampMixin, db.Model):
    """Home sample collection details associated 1-to-1 with a Booking."""

    __tablename__ = "home_visits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED', 'SCHEDULED', 'DISPATCHED', 'SAMPLE_COLLECTED', 'CANCELLED')",
            name="ck_home_visits_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED", nullable=False)

    booking: Mapped[Booking] = relationship("Booking", back_populates="home_visit")

    def __repr__(self) -> str:
        return f"<HomeVisit id={self.id} booking_id={self.booking_id} area='{self.area}' status='{self.status}'>"
