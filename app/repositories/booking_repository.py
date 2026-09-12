"""Repository for Booking and HomeVisit entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.booking import Booking


class BookingRepository:
    """Data access repository for booking records, line items, and home visits."""

    def get_by_id(self, booking_id: int) -> Booking | None:
        """Fetch booking by primary key ID with all associations loaded."""
        stmt = (
            select(Booking)
            .where(Booking.id == booking_id)
            .options(
                selectinload(Booking.customer),
                selectinload(Booking.branch),
                selectinload(Booking.slot),
                selectinload(Booking.items),
                selectinload(Booking.home_visit),
            )
        )
        return db.session.execute(stmt).scalar_one_or_none()

    def get_by_reference(self, reference: str, for_update: bool = False) -> Booking | None:
        """Fetch booking by unique human-readable reference, optionally locking the row."""
        stmt = (
            select(Booking)
            .where(Booking.booking_reference == reference.strip().upper())
            .options(
                selectinload(Booking.customer),
                selectinload(Booking.branch),
                selectinload(Booking.slot),
                selectinload(Booking.items),
                selectinload(Booking.home_visit),
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        return db.session.execute(stmt).scalar_one_or_none()

    def get_by_idempotency_key(self, idempotency_key: str) -> Booking | None:
        """Fetch booking by unique client idempotency key."""
        stmt = (
            select(Booking)
            .where(Booking.idempotency_key == idempotency_key.strip())
            .options(
                selectinload(Booking.customer),
                selectinload(Booking.branch),
                selectinload(Booking.slot),
                selectinload(Booking.items),
                selectinload(Booking.home_visit),
            )
        )
        return db.session.execute(stmt).scalar_one_or_none()

    def add(self, booking: Booking) -> None:
        """Attach a new booking entity to the persistence session."""
        db.session.add(booking)

    def flush(self) -> None:
        """Flush pending changes to the database within the current transaction."""
        db.session.flush()
