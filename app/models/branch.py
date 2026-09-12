"""Branch and AvailabilitySlot models for appointment scheduling."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSON_VARIANT, TimestampMixin


class Branch(TimestampMixin, db.Model):
    """Physical diagnostic laboratory branch."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    opening_hours_json: Mapped[dict[str, Any]] = mapped_column(
        JSON_VARIANT,
        nullable=False,
        default=dict,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    slots: Mapped[list[AvailabilitySlot]] = relationship(
        "AvailabilitySlot",
        back_populates="branch",
    )

    def __repr__(self) -> str:
        return f"<Branch id={self.id} name='{self.name}'>"


class AvailabilitySlot(db.Model):
    """Appointment availability slot for either branch or home visits."""

    __tablename__ = "availability_slots"
    __table_args__ = (
        CheckConstraint("capacity >= 0", name="ck_slots_capacity_non_negative"),
        CheckConstraint("reserved_count >= 0", name="ck_slots_reserved_non_negative"),
        CheckConstraint("reserved_count <= capacity", name="ck_slots_reserved_le_capacity"),
        CheckConstraint("visit_type IN ('BRANCH', 'HOME')", name="ck_slots_visit_type"),
        CheckConstraint(
            "(visit_type = 'BRANCH' AND branch_id IS NOT NULL) OR (visit_type = 'HOME' AND branch_id IS NULL)",
            name="ck_slots_branch_for_branch_visit",
        ),
        # Distinct partial uniqueness: BRANCH requires branch_id, HOME enforces pool slot uniqueness without branch_id
        Index(
            "uq_slots_branch_date_time",
            "branch_id",
            "date",
            "time",
            unique=True,
            postgresql_where=text("visit_type = 'BRANCH'"),
        ),
        Index(
            "uq_slots_home_date_time",
            "date",
            "time",
            unique=True,
            postgresql_where=text("visit_type = 'HOME' AND branch_id IS NULL"),
        ),
        Index("ix_slots_branch_date_active", "branch_id", "date", "active"),
        Index("ix_slots_visit_type_date", "visit_type", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    visit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    time: Mapped[time] = mapped_column(Time, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reserved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    branch: Mapped[Branch | None] = relationship("Branch", back_populates="slots")

    @property
    def is_available(self) -> bool:
        """Return True if the slot is active and has remaining capacity."""
        return self.active and (self.reserved_count < self.capacity)

    def __repr__(self) -> str:
        return (
            f"<AvailabilitySlot id={self.id} type='{self.visit_type}' "
            f"date={self.date} time={self.time} reserved={self.reserved_count}/{self.capacity}>"
        )
