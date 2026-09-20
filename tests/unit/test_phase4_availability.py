"""Unit tests for Phase 4 booking availability and slot scheduling rules.

Covers criteria 1-8:
1) Valid free 16:00 slot -> available
2) Same 16:00 after booking -> full/unavailable
3) 16:30 remains independently available
4) 16:05 -> invalid exact slot
5) Before opening (08:30) -> invalid
6) Closing time (19:00) / after closing (19:30) -> invalid
7) Inactive slot -> invalid
8) Inactive branch -> invalid
Plus: deterministic nearby alternatives without silent rounding.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest
from flask import Flask

from app.extensions import db
from app.models.branch import AvailabilitySlot, Branch
from app.models.test import LabTest, TestCategory
from app.services.booking_service import BookingService


@pytest.fixture
def availability_catalog(app: Flask):
    """Seed branches and discrete 30-minute slots for deterministic testing."""
    with app.app_context():
        db.create_all()

        cat = TestCategory(name="Hematology", slug="hematology", active=True)
        db.session.add(cat)
        db.session.flush()

        test_cbc = LabTest(
            code="CBC",
            name="Complete Blood Count",
            category_id=cat.id,
            short_description="Blood health screen",
            sample_type="Whole Blood",
            price=Decimal("250.00"),
            result_turnaround_text="4 hours",
            active=True,
        )
        db.session.add(test_cbc)

        # Active branch: 09:00 - 19:00
        branch_active = Branch(
            name="Nasr City Branch",
            address="45 Abbas El Akkad, Nasr City, Cairo",
            phone="+20224012345",
            opening_hours_json={
                "regular": "09:00 - 19:00",
                "monday": "09:00 - 19:00",
                "tuesday": "09:00 - 19:00",
                "wednesday": "09:00 - 19:00",
                "thursday": "09:00 - 19:00",
                "friday": "09:00 - 19:00",
                "saturday": "09:00 - 19:00",
                "sunday": "09:00 - 19:00",
            },
            active=True,
        )
        # Inactive branch
        branch_inactive = Branch(
            name="Renovating Branch",
            address="12 Closed St, Cairo",
            phone="+20224099999",
            opening_hours_json={"regular": "09:00 - 19:00"},
            active=False,
        )
        db.session.add_all([branch_active, branch_inactive])
        db.session.flush()

        test_date = date(2026, 9, 21)

        # Discrete 30-minute slots with capacity=1
        slot_1600 = AvailabilitySlot(
            branch_id=branch_active.id,
            visit_type="BRANCH",
            date=test_date,
            time=time(16, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        slot_1630 = AvailabilitySlot(
            branch_id=branch_active.id,
            visit_type="BRANCH",
            date=test_date,
            time=time(16, 30),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        slot_1700 = AvailabilitySlot(
            branch_id=branch_active.id,
            visit_type="BRANCH",
            date=test_date,
            time=time(17, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        # Inactive slot
        slot_inactive = AvailabilitySlot(
            branch_id=branch_active.id,
            visit_type="BRANCH",
            date=test_date,
            time=time(11, 0),
            capacity=1,
            reserved_count=0,
            active=False,
        )
        # Slot on inactive branch (different date to stay cleanly segregated)
        slot_on_inactive_branch = AvailabilitySlot(
            branch_id=branch_inactive.id,
            visit_type="BRANCH",
            date=date(2026, 9, 22),
            time=time(16, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )

        db.session.add_all(
            [slot_1600, slot_1630, slot_1700, slot_inactive, slot_on_inactive_branch]
        )
        db.session.commit()

        yield {
            "branch_active": branch_active,
            "branch_inactive": branch_inactive,
            "test_cbc": test_cbc,
            "test_date": test_date,
            "slot_1600": slot_1600,
            "slot_1630": slot_1630,
            "slot_1700": slot_1700,
            "slot_inactive": slot_inactive,
        }


def test_rule_1_valid_free_1600_slot_is_available(app: Flask, availability_catalog: dict) -> None:
    """Criteria 1: Valid free 16:00 slot is available."""
    with app.app_context():
        service = BookingService()
        res = service.check_branch_availability(
            branch_id=availability_catalog["branch_active"].id,
            visit_type="BRANCH",
            target_date=availability_catalog["test_date"],
            target_time=time(16, 0),
        )
        assert res["available"] is True
        assert res["status"] == "AVAILABLE"
        assert res["slot_id"] == availability_catalog["slot_1600"].id


def test_rule_2_and_3_slot_full_after_booking_and_adjacent_remains_free(
    app: Flask, availability_catalog: dict
) -> None:
    """Criteria 2 & 3: Once 16:00 is booked (capacity 1), it becomes full, but 16:30 remains free."""
    with app.app_context():
        service = BookingService()
        branch_id = availability_catalog["branch_active"].id
        target_date = availability_catalog["test_date"]

        # Book 16:00
        booking = service.create_branch_booking(
            customer_name="Ahmed Ali",
            customer_phone="+201012345678",
            branch_id=branch_id,
            slot_id=availability_catalog["slot_1600"].id,
            idempotency_key="idemp-rule-2-1600",
            test_ids=[availability_catalog["test_cbc"].id],
        )
        assert booking is not None
        assert booking.status == "CONFIRMED"

        # Criteria 2: Check 16:00 again -> full/unavailable
        res_1600 = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(16, 0),
        )
        assert res_1600["available"] is False
        assert res_1600["status"] == "SLOT_FULL"
        assert any(alt["time"] == "16:30" for alt in res_1600["alternatives"])

        # Criteria 3: 16:30 remains independently available
        res_1630 = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(16, 30),
        )
        assert res_1630["available"] is True
        assert res_1630["status"] == "AVAILABLE"


def test_rule_4_invalid_exact_slot_1605_never_rounded_silently(
    app: Flask, availability_catalog: dict
) -> None:
    """Criteria 4: 16:05 is not a valid 30-min slot. Never round silently, offer nearby real slots."""
    with app.app_context():
        service = BookingService()
        branch_id = availability_catalog["branch_active"].id
        target_date = availability_catalog["test_date"]

        res = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(16, 5),
        )
        assert res["available"] is False
        assert res["status"] == "INVALID_TIME"
        assert "not a valid 30-minute slot" in res["reason"]
        # Must return real available alternatives such as 16:00 or 16:30
        assert len(res["alternatives"]) > 0
        alt_times = [alt["time"] for alt in res["alternatives"]]
        assert "16:00" in alt_times or "16:30" in alt_times


def test_rule_5_before_opening_is_invalid(app: Flask, availability_catalog: dict) -> None:
    """Criteria 5: 08:30 is before opening (09:00). Invalid operating hours."""
    with app.app_context():
        service = BookingService()
        branch_id = availability_catalog["branch_active"].id
        target_date = availability_catalog["test_date"]

        res = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(8, 30),
        )
        assert res["available"] is False
        assert res["status"] == "OUTSIDE_HOURS"
        assert "09:00" in res["reason"]


def test_rule_6_closing_time_1900_is_not_a_valid_appointment_start(
    app: Flask, availability_catalog: dict
) -> None:
    """Criteria 6: 19:00 is branch closing time, NOT a valid appointment start. 19:30 is after closing."""
    with app.app_context():
        service = BookingService()
        branch_id = availability_catalog["branch_active"].id
        target_date = availability_catalog["test_date"]

        # 19:00 is closing time
        res_1900 = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(19, 0),
        )
        assert res_1900["available"] is False
        assert res_1900["status"] == "OUTSIDE_HOURS"

        # 19:30 is after closing
        res_1930 = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(19, 30),
        )
        assert res_1930["available"] is False
        assert res_1930["status"] == "OUTSIDE_HOURS"


def test_rule_7_inactive_slot_is_unavailable(app: Flask, availability_catalog: dict) -> None:
    """Criteria 7: Inactive slot cannot be booked."""
    with app.app_context():
        service = BookingService()
        branch_id = availability_catalog["branch_active"].id
        target_date = availability_catalog["test_date"]

        res = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(11, 0),
        )
        assert res["available"] is False
        assert res["status"] in ("SLOT_INACTIVE", "SLOT_NOT_FOUND")


def test_rule_8_inactive_branch_cannot_be_booked(app: Flask, availability_catalog: dict) -> None:
    """Criteria 8: Inactive branch returns BRANCH_INACTIVE."""
    with app.app_context():
        service = BookingService()
        branch_id = availability_catalog["branch_inactive"].id
        target_date = date(2026, 9, 22)

        res = service.check_branch_availability(
            branch_id=branch_id,
            visit_type="BRANCH",
            target_date=target_date,
            target_time=time(16, 0),
        )
        assert res["available"] is False
        assert res["status"] == "BRANCH_INACTIVE"


def test_validate_appointment_time_helper() -> None:
    """Direct verification of validate_appointment_time helper for 30m grid."""
    service = BookingService()

    # Valid times
    valid, reason = service.validate_appointment_time(time(9, 0))
    assert valid is True
    assert reason is None

    valid, reason = service.validate_appointment_time(time(16, 30))
    assert valid is True
    assert reason is None

    valid, reason = service.validate_appointment_time(time(18, 30))
    assert valid is True
    assert reason is None

    # Invalid minute
    valid, reason = service.validate_appointment_time(time(16, 15))
    assert valid is False
    assert reason == "INVALID_INTERVAL"

    # Outside hours
    valid, reason = service.validate_appointment_time(time(8, 30))
    assert valid is False
    assert reason == "BEFORE_OPENING_HOURS"

    valid, reason = service.validate_appointment_time(time(19, 0))
    assert valid is False
    assert reason == "OUTSIDE_OPENING_HOURS"
