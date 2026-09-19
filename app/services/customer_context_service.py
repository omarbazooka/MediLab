"""Bounded, read-only customer context service for agent reasoning."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.booking import Booking, BookingItem
from app.models.customer import Customer


class CustomerContextService:
    """Service providing bounded, read-only customer historical facts."""

    def get_customer_context(
        self,
        customer_id: int | None,
        max_bookings: int = 5,
    ) -> dict[str, Any] | None:
        """Retrieve bounded historical booking facts strictly isolated to customer_id."""
        if customer_id is None:
            return None

        customer = db.session.get(Customer, customer_id)
        if customer is None:
            return None

        # Retrieve recent bookings ordered by date descending
        stmt = (
            select(Booking)
            .where(Booking.customer_id == customer_id)
            .options(
                selectinload(Booking.items).selectinload(BookingItem.test),
                selectinload(Booking.items).selectinload(BookingItem.package),
                selectinload(Booking.branch),
            )
            .order_by(Booking.scheduled_date.desc(), Booking.scheduled_time.desc())
            .limit(max_bookings)
        )
        bookings = list(db.session.execute(stmt).scalars().all())

        booking_summaries: list[dict[str, Any]] = []
        for b in bookings:
            services: list[str] = []
            for item in b.items:
                if item.test:
                    services.append(item.test.name)
                elif item.package:
                    services.append(item.package.name)

            booking_summaries.append(
                {
                    "booking_reference": b.booking_reference,
                    "scheduled_date": b.scheduled_date.isoformat(),
                    "scheduled_time": b.scheduled_time.strftime("%H:%M"),
                    "status": b.status,
                    "visit_type": b.visit_type,
                    "branch_name": b.branch.name if b.branch else None,
                    "items": services,
                    "total_price": f"{b.total_price:.2f} EGP",
                    "cancelled_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
                }
            )

        latest_booking = booking_summaries[0] if booking_summaries else None
        latest_service = (
            latest_booking["items"][0] if latest_booking and latest_booking["items"] else None
        )

        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "customer_phone": customer.phone,
            "recent_bookings": booking_summaries,
            "bookings": booking_summaries,  # convenience alias
            "latest_booking": latest_booking,
            "latest_service": latest_service,
            "has_active_booking": any(b["status"] == "CONFIRMED" for b in booking_summaries),
            "has_cancellations": any(b["status"] == "CANCELLED" for b in booking_summaries),
        }
