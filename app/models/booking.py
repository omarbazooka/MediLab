"""Booking and BookingItem models for appointment management."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.branch import AvailabilitySlot, Branch
    from app.models.customer import Customer
    from app.models.home_visit import HomeVisit
    from app.models.package import Package
    from app.models.test import LabTest


class Booking(TimestampMixin, db.Model):
    """Customer appointment booking for lab or home tests."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("visit_type IN ('BRANCH', 'HOME')", name="ck_bookings_visit_type"),
        CheckConstraint(
            "status IN ('CONFIRMED', 'COMPLETED', 'CANCELLED')",
            name="ck_bookings_status",
        ),
        CheckConstraint(
            "(visit_type = 'BRANCH' AND branch_id IS NOT NULL) OR (visit_type = 'HOME' AND branch_id IS NULL)",
            name="ck_bookings_branch_for_branch_visit",
        ),
        Index("ix_bookings_customer_id", "customer_id"),
        Index("ix_bookings_scheduled_date", "scheduled_date"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_slot_id", "availability_slot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_reference: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Authoritative link to the reserved availability slot
    availability_slot_id: Mapped[int] = mapped_column(
        ForeignKey("availability_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    visit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Historical snapshots of appointment details at the time of booking
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="CONFIRMED", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship("Customer")
    branch: Mapped[Branch | None] = relationship("Branch")
    slot: Mapped[AvailabilitySlot] = relationship("AvailabilitySlot")
    items: Mapped[list[BookingItem]] = relationship(
        "BookingItem",
        back_populates="booking",
        cascade="all, delete-orphan",
    )
    home_visit: Mapped[HomeVisit | None] = relationship(
        "HomeVisit",
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def total_price(self) -> Decimal:
        """Calculate total booked price from item snapshots."""
        return sum((item.unit_price_snapshot for item in self.items), Decimal("0.00"))

    def __repr__(self) -> str:
        return f"<Booking id={self.id} ref='{self.booking_reference}' status='{self.status}'>"


class BookingItem(db.Model):
    """Line item in a booking representing a specific test or package."""

    __tablename__ = "booking_items"
    __table_args__ = (
        CheckConstraint(
            "unit_price_snapshot >= 0",
            name="ck_booking_items_price_non_negative",
        ),
        CheckConstraint(
            "(test_id IS NOT NULL AND package_id IS NULL) OR (test_id IS NULL AND package_id IS NOT NULL)",
            name="ck_booking_items_single_item_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    test_id: Mapped[int | None] = mapped_column(
        ForeignKey("lab_tests.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    booking: Mapped[Booking] = relationship("Booking", back_populates="items")
    test: Mapped[LabTest | None] = relationship("LabTest")
    package: Mapped[Package | None] = relationship("Package")

    def __repr__(self) -> str:
        return (
            f"<BookingItem id={self.id} booking_id={self.booking_id} "
            f"test_id={self.test_id} package_id={self.package_id} price={self.unit_price_snapshot}>"
        )
