"""Unit tests for Phase 4 booking cancellation and status checking with customer scoping.

Covers criteria 22-29:
22) Correct booking becomes CANCELLED with cancelled_at set
23) Cancellation releases exact slot capacity (reserved_count = max(reserved_count - 1, 0))
24) Released slot becomes available again for new bookings
25) Repeated cancellation is controlled and idempotent
26) Wrong customer/session cannot cancel unrelated booking (ownership enforcement)
27) Known reference returns true DB status
28) Unknown reference handled safely
29) Wrong scope does not leak unrelated booking
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest
from flask import Flask

from app.extensions import db
from app.models.booking import Booking
from app.models.branch import AvailabilitySlot, Branch
from app.models.test import LabTest, TestCategory
from app.services.booking_service import (
    BookingNotFoundError,
    BookingService,
    BookingValidationError,
)


@pytest.fixture
def cancellation_catalog(app: Flask):
    """Seed branch, slot, test, and two distinct customer bookings for scoped testing."""
    with app.app_context():
        db.create_all()

        cat = TestCategory(name="Biochemistry", slug="biochemistry", active=True)
        db.session.add(cat)
        db.session.flush()

        test_cbc = LabTest(
            code="CBC",
            name="Complete Blood Count",
            category_id=cat.id,
            short_description="Blood test",
            sample_type="Whole Blood",
            price=Decimal("250.00"),
            result_turnaround_text="4 hours",
            active=True,
        )
        branch = Branch(
            name="Heliopolis Branch",
            address="10 Baghdad St, Heliopolis, Cairo",
            phone="+20224151234",
            opening_hours_json={"regular": "09:00 - 19:00"},
            active=True,
        )
        db.session.add_all([test_cbc, branch])
        db.session.flush()

        test_date = date(2026, 9, 24)

        # Slot with capacity=1
        slot = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=test_date,
            time=time(12, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        db.session.add(slot)
        db.session.commit()

        service = BookingService()

        # Customer 1 booking
        booking_customer1 = service.create_branch_booking(
            customer_name="Customer One",
            customer_phone="+201011110001",
            branch_id=branch.id,
            slot_id=slot.id,
            idempotency_key="idemp-cancel-c1",
            test_ids=[test_cbc.id],
        )

        yield {
            "branch": branch,
            "slot": slot,
            "test_cbc": test_cbc,
            "booking1": booking_customer1,
            "customer1_id": booking_customer1.customer_id,
            "customer1_phone": "+201011110001",
            "unrelated_phone": "+201099990002",
        }


def test_rule_22_23_24_cancel_booking_and_slot_released(
    app: Flask, cancellation_catalog: dict
) -> None:
    """Criteria 22, 23, 24: Cancellation sets status to CANCELLED and cancelled_at, decrements slot reserved_count, making it available again."""
    with app.app_context():
        service = BookingService()
        booking = cancellation_catalog["booking1"]
        slot_id = cancellation_catalog["slot"].id

        # Verify slot is currently full
        slot_before = db.session.get(AvailabilitySlot, slot_id)
        assert slot_before.reserved_count == 1
        assert slot_before.is_available is False

        # Criteria 22: Cancel booking
        cancelled = service.cancel_booking(
            reference=booking.booking_reference,
            customer_id=cancellation_catalog["customer1_id"],
        )

        assert cancelled.status == "CANCELLED"
        assert cancelled.cancelled_at is not None

        # Criteria 23: Exact slot reserved_count decremented
        slot_after = db.session.get(AvailabilitySlot, slot_id)
        assert slot_after.reserved_count == 0

        # Criteria 24: Released slot is available again for new bookings
        assert slot_after.is_available is True
        avail = service.check_branch_availability(
            branch_id=cancellation_catalog["branch"].id,
            visit_type="BRANCH",
            target_date=slot_after.date,
            target_time=slot_after.time,
        )
        assert avail["available"] is True
        assert avail["status"] == "AVAILABLE"


def test_rule_25_repeated_cancellation_is_controlled_and_idempotent(
    app: Flask, cancellation_catalog: dict
) -> None:
    """Criteria 25: Repeated cancellation of already cancelled booking is safe, idempotent, and does not decrement slot below 0."""
    with app.app_context():
        service = BookingService()
        booking = cancellation_catalog["booking1"]
        slot_id = cancellation_catalog["slot"].id

        # 1st cancel
        cancelled_1 = service.cancel_booking(
            reference=booking.booking_reference,
            customer_phone=cancellation_catalog["customer1_phone"],
        )
        assert cancelled_1.status == "CANCELLED"

        slot_after_first = db.session.get(AvailabilitySlot, slot_id).reserved_count
        assert slot_after_first == 0

        # 2nd cancel (repeated)
        cancelled_2 = service.cancel_booking(
            reference=booking.booking_reference,
            customer_phone=cancellation_catalog["customer1_phone"],
        )
        assert cancelled_2.status == "CANCELLED"

        # Slot capacity must not be decremented below 0
        slot_after_second = db.session.get(AvailabilitySlot, slot_id).reserved_count
        assert slot_after_second == 0


def test_rule_26_wrong_customer_cannot_cancel_unrelated_booking(
    app: Flask, cancellation_catalog: dict
) -> None:
    """Criteria 26: Attempting to cancel another customer's booking with mismatched customer_id or phone fails with BookingValidationError."""
    with app.app_context():
        service = BookingService()
        booking = cancellation_catalog["booking1"]

        # Attempt cancel with wrong phone
        with pytest.raises(BookingValidationError, match="not authorized"):
            service.cancel_booking(
                reference=booking.booking_reference,
                customer_phone=cancellation_catalog["unrelated_phone"],
            )

        # Attempt cancel with wrong customer_id
        with pytest.raises(BookingValidationError, match="not authorized"):
            service.cancel_booking(
                reference=booking.booking_reference,
                customer_id=999999,
            )

        # Booking must remain CONFIRMED
        booking_reloaded = db.session.get(Booking, booking.id)
        assert booking_reloaded.status == "CONFIRMED"


def test_rule_27_known_reference_returns_true_status(
    app: Flask, cancellation_catalog: dict
) -> None:
    """Criteria 27: Known booking reference returns true current DB status."""
    with app.app_context():
        service = BookingService()
        booking = cancellation_catalog["booking1"]

        status_result = service.get_booking_status(
            reference=booking.booking_reference,
            customer_id=cancellation_catalog["customer1_id"],
        )
        assert status_result is not None
        assert status_result.status == "CONFIRMED"
        assert status_result.booking_reference == booking.booking_reference


def test_rule_28_unknown_reference_handled_safely(app: Flask) -> None:
    """Criteria 28: Unknown reference handled safely without errors or hallucinations."""
    with app.app_context():
        db.create_all()
        service = BookingService()

        # Query unknown reference
        res = service.get_booking_status("MLB-99999999-NONEXIST")
        assert res is None

        # Cancel unknown reference throws BookingNotFoundError
        with pytest.raises(BookingNotFoundError):
            service.cancel_booking("MLB-99999999-NONEXIST")


def test_rule_29_wrong_scope_does_not_leak_unrelated_booking(
    app: Flask, cancellation_catalog: dict
) -> None:
    """Criteria 29: Reading booking status with wrong customer scope returns None and does not leak details."""
    with app.app_context():
        service = BookingService()
        booking = cancellation_catalog["booking1"]

        # Status check with unrelated phone
        res_phone = service.get_booking_status(
            reference=booking.booking_reference,
            customer_phone=cancellation_catalog["unrelated_phone"],
        )
        assert res_phone is None

        # Status check with unrelated customer_id
        res_id = service.get_booking_status(
            reference=booking.booking_reference,
            customer_id=999999,
        )
        assert res_id is None
