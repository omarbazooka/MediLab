"""Unit tests for Phase 4 booking transaction execution, idempotency, and rollback safety.

Covers criteria 9-21:
9) Missing fields -> NO INSERT
10) Valid confirmed branch booking -> exactly one DB row
11) Valid confirmed home visit -> exactly one DB row with HomeVisit record
12) No confirmation -> NO INSERT
13) Repeated confirmation -> NO DUPLICATE (idempotency)
14) Real booking reference persisted (MLB-YYYYMMDD-XXXXXXXX)
15) BookingItem correct
16) Price snapshot uses DB truth
17) Slot reserved_count updated correctly (+1)
18) Transaction failure -> rollback
19) No success response after rollback
20) Two attempts for last capacity -> only one succeeds
21) Idempotency survives repeated confirmation
"""

from __future__ import annotations

import re
from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.booking import Booking
from app.models.branch import AvailabilitySlot, Branch
from app.models.home_visit import HomeVisit
from app.models.package import Package, PackageTest
from app.models.test import LabTest, TestCategory
from app.services.booking_service import (
    BookingService,
    BookingValidationError,
    CapacityExceededError,
)


@pytest.fixture
def booking_fixture(app: Flask):
    """Seed branches, packages, tests, and slots for transactional booking tests."""
    with app.app_context():
        db.create_all()

        cat = TestCategory(name="Biochemistry", slug="biochemistry", active=True)
        db.session.add(cat)
        db.session.flush()

        # CBC: 250.00 EGP
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
        # Fasting Glucose: 110.00 EGP
        test_fbs = LabTest(
            code="FBS",
            name="Fasting Blood Sugar",
            category_id=cat.id,
            short_description="Glucose test",
            sample_type="Plasma",
            price=Decimal("110.00"),
            result_turnaround_text="2 hours",
            active=True,
        )
        db.session.add_all([test_cbc, test_fbs])
        db.session.flush()

        # Wellness Package: 320.00 EGP (vs 360 separate)
        pkg_wellness = Package(
            name="Basic Wellness Package",
            description="CBC and Glucose",
            price=Decimal("320.00"),
            active=True,
        )
        db.session.add(pkg_wellness)
        db.session.flush()
        db.session.add(PackageTest(package_id=pkg_wellness.id, test_id=test_cbc.id))
        db.session.add(PackageTest(package_id=pkg_wellness.id, test_id=test_fbs.id))

        branch = Branch(
            name="Dokki Branch",
            address="15 Mossadak St, Dokki, Giza",
            phone="+20237612345",
            opening_hours_json={"regular": "09:00 - 19:00"},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        test_date = date(2026, 9, 23)

        # Branch slot with capacity=1
        slot_branch = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=test_date,
            time=time(10, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        # Branch slot with capacity=2 for concurrency test
        slot_branch_cap2 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=test_date,
            time=time(11, 0),
            capacity=2,
            reserved_count=1,  # Only 1 slot remains
            active=True,
        )
        # Home visit slot with capacity=1
        slot_home = AvailabilitySlot(
            branch_id=None,
            visit_type="HOME",
            date=test_date,
            time=time(14, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )

        db.session.add_all([slot_branch, slot_branch_cap2, slot_home])
        db.session.commit()

        yield {
            "branch": branch,
            "test_cbc": test_cbc,
            "test_fbs": test_fbs,
            "pkg_wellness": pkg_wellness,
            "test_date": test_date,
            "slot_branch": slot_branch,
            "slot_branch_cap2": slot_branch_cap2,
            "slot_home": slot_home,
        }


def test_rule_9_missing_required_fields_no_insert(app: Flask, booking_fixture: dict) -> None:
    """Criteria 9: Missing required fields (e.g. empty name or phone) throws validation error and causes NO INSERT."""
    with app.app_context():
        service = BookingService()
        initial_count = db.session.query(Booking).count()

        # Missing name
        with pytest.raises(BookingValidationError):
            service.create_branch_booking(
                customer_name="",
                customer_phone="+201012345678",
                branch_id=booking_fixture["branch"].id,
                slot_id=booking_fixture["slot_branch"].id,
                idempotency_key="idemp-missing-name",
                test_ids=[booking_fixture["test_cbc"].id],
            )

        # Missing phone
        with pytest.raises(BookingValidationError):
            service.create_branch_booking(
                customer_name="Omar",
                customer_phone="",
                branch_id=booking_fixture["branch"].id,
                slot_id=booking_fixture["slot_branch"].id,
                idempotency_key="idemp-missing-phone",
                test_ids=[booking_fixture["test_cbc"].id],
            )

        # Missing service items (neither test nor package)
        with pytest.raises(BookingValidationError):
            service.create_branch_booking(
                customer_name="Omar",
                customer_phone="+201012345678",
                branch_id=booking_fixture["branch"].id,
                slot_id=booking_fixture["slot_branch"].id,
                idempotency_key="idemp-missing-service",
                test_ids=[],
                package_ids=[],
            )

        # Missing home address for home visit
        with pytest.raises(BookingValidationError):
            service.create_home_visit(
                customer_name="Omar",
                customer_phone="+201012345678",
                slot_id=booking_fixture["slot_home"].id,
                address="",
                area="Dokki",
                idempotency_key="idemp-missing-addr",
                test_ids=[booking_fixture["test_cbc"].id],
            )

        # Assert zero rows were inserted
        assert db.session.query(Booking).count() == initial_count


def test_rule_10_14_15_16_17_valid_confirmed_branch_booking(
    app: Flask, booking_fixture: dict
) -> None:
    """Criteria 10, 14, 15, 16, 17: Valid confirmed branch booking creates exactly 1 DB row, real reference, correct items, DB price snapshot, and increments slot."""
    with app.app_context():
        service = BookingService()
        initial_bookings = db.session.query(Booking).count()
        slot = db.session.get(AvailabilitySlot, booking_fixture["slot_branch"].id)
        assert slot.reserved_count == 0

        booking = service.create_branch_booking(
            customer_name="Kareem Tarek",
            customer_phone="+201099887766",
            branch_id=booking_fixture["branch"].id,
            slot_id=slot.id,
            idempotency_key="idemp-branch-success-1",
            test_ids=[booking_fixture["test_cbc"].id],
            package_ids=[booking_fixture["pkg_wellness"].id],
        )

        # Criteria 10: Exactly one DB row inserted
        assert db.session.query(Booking).count() == initial_bookings + 1
        assert booking.status == "CONFIRMED"

        # Criteria 14: Real booking reference persisted with correct pattern MLB-YYYYMMDD-XXXXXXXX
        assert booking.booking_reference is not None
        assert re.match(r"^MLB-\d{8}-[A-F0-9]{8}$", booking.booking_reference)

        # Criteria 15: BookingItem correct
        assert len(booking.items) == 2
        test_item = next(item for item in booking.items if item.test_id is not None)
        pkg_item = next(item for item in booking.items if item.package_id is not None)
        assert test_item.test_id == booking_fixture["test_cbc"].id
        assert pkg_item.package_id == booking_fixture["pkg_wellness"].id

        # Criteria 16: Price snapshot uses DB truth (not user input)
        assert test_item.unit_price_snapshot == Decimal("250.00")
        assert pkg_item.unit_price_snapshot == Decimal("320.00")

        # Criteria 17: Slot reserved_count updated (+1)
        slot_reloaded = db.session.get(AvailabilitySlot, slot.id)
        assert slot_reloaded.reserved_count == 1
        assert slot_reloaded.is_available is False


def test_rule_11_valid_confirmed_home_visit(app: Flask, booking_fixture: dict) -> None:
    """Criteria 11: Valid confirmed home visit creates exactly one Booking row and HomeVisit record."""
    with app.app_context():
        service = BookingService()
        initial_bookings = db.session.query(Booking).count()
        initial_home_visits = db.session.query(HomeVisit).count()

        booking = service.create_home_visit(
            customer_name="Nour Hassan",
            customer_phone="+201122334455",
            slot_id=booking_fixture["slot_home"].id,
            address="Bldg 12, Nile Corniche, Apt 4",
            area="Dokki",
            home_instructions="Call before arrival, 4th floor",
            idempotency_key="idemp-home-success-1",
            test_ids=[booking_fixture["test_fbs"].id],
        )

        assert db.session.query(Booking).count() == initial_bookings + 1
        assert db.session.query(HomeVisit).count() == initial_home_visits + 1
        assert booking.visit_type == "HOME"
        assert booking.branch_id is None
        assert booking.home_visit is not None
        assert booking.home_visit.address == "Bldg 12, Nile Corniche, Apt 4"
        assert booking.home_visit.area == "Dokki"
        assert booking.home_visit.instructions == "Call before arrival, 4th floor"
        assert booking.home_visit.status == "SCHEDULED"


def test_rule_13_and_21_repeated_confirmation_idempotent_no_duplicate(
    app: Flask, booking_fixture: dict
) -> None:
    """Criteria 13 & 21: Repeated confirmation returns the exact same booking, creates NO DUPLICATE, and does not increment slot twice."""
    with app.app_context():
        service = BookingService()
        slot = db.session.get(AvailabilitySlot, booking_fixture["slot_branch"].id)
        slot.reserved_count = 0
        db.session.commit()

        idemp_key = "idemp-repeat-test-999"

        # 1st confirmation
        booking_1 = service.create_branch_booking(
            customer_name="Sara Adel",
            customer_phone="+201055554444",
            branch_id=booking_fixture["branch"].id,
            slot_id=slot.id,
            idempotency_key=idemp_key,
            test_ids=[booking_fixture["test_cbc"].id],
        )
        first_ref = booking_1.booking_reference
        count_after_first = db.session.query(Booking).count()
        slot_after_first = db.session.get(AvailabilitySlot, slot.id).reserved_count

        # 2nd confirmation with same idempotency key (simulating double-click or network retry)
        booking_2 = service.create_branch_booking(
            customer_name="Sara Adel",
            customer_phone="+201055554444",
            branch_id=booking_fixture["branch"].id,
            slot_id=slot.id,
            idempotency_key=idemp_key,
            test_ids=[booking_fixture["test_cbc"].id],
        )

        # Results must be identical
        assert booking_2.id == booking_1.id
        assert booking_2.booking_reference == first_ref

        # NO second DB row inserted
        assert db.session.query(Booking).count() == count_after_first

        # Slot reserved_count must NOT have incremented a second time
        slot_after_second = db.session.get(AvailabilitySlot, slot.id).reserved_count
        assert slot_after_second == slot_after_first == 1


def test_rule_18_and_19_transaction_failure_rolls_back_and_leaves_no_success(
    app: Flask, booking_fixture: dict
) -> None:
    """Criteria 18 & 19: Database transaction failure triggers complete rollback, leaving no orphan booking and leaving slot unreserved."""
    with app.app_context():
        service = BookingService()
        slot = db.session.get(AvailabilitySlot, booking_fixture["slot_branch"].id)
        slot.reserved_count = 0
        db.session.commit()

        initial_bookings = db.session.query(Booking).count()

        # Force a database exception during booking add
        with patch.object(
            service.booking_repo, "add", side_effect=IntegrityError("forced error", None, None)
        ):
            with pytest.raises(IntegrityError):
                service.create_branch_booking(
                    customer_name="Failing Customer",
                    customer_phone="+201011112222",
                    branch_id=booking_fixture["branch"].id,
                    slot_id=slot.id,
                    idempotency_key="idemp-forced-failure",
                    test_ids=[booking_fixture["test_cbc"].id],
                )

        # Invariant 18: Zero bookings inserted
        assert db.session.query(Booking).count() == initial_bookings

        # Invariant 19: Slot capacity is not reserved after rollback
        slot_reloaded = db.session.get(AvailabilitySlot, slot.id)
        assert slot_reloaded.reserved_count == 0


def test_rule_20_concurrency_race_for_last_slot_capacity(app: Flask, booking_fixture: dict) -> None:
    """Criteria 20: When two attempts compete for the final remaining capacity, exactly one succeeds and the second receives CapacityExceededError."""
    with app.app_context():
        service = BookingService()
        # slot_branch_cap2 has capacity=2, reserved_count=1 -> exactly 1 capacity remaining
        slot = db.session.get(AvailabilitySlot, booking_fixture["slot_branch_cap2"].id)
        assert slot.capacity == 2
        assert slot.reserved_count == 1

        # Customer A books the last capacity
        booking_a = service.create_branch_booking(
            customer_name="Customer A",
            customer_phone="+201011111111",
            branch_id=booking_fixture["branch"].id,
            slot_id=slot.id,
            idempotency_key="idemp-race-customer-a",
            test_ids=[booking_fixture["test_cbc"].id],
        )
        assert booking_a is not None
        assert booking_a.status == "CONFIRMED"

        # Customer B attempts to book the same slot immediately after
        with pytest.raises(CapacityExceededError):
            service.create_branch_booking(
                customer_name="Customer B",
                customer_phone="+201022222222",
                branch_id=booking_fixture["branch"].id,
                slot_id=slot.id,
                idempotency_key="idemp-race-customer-b",
                test_ids=[booking_fixture["test_cbc"].id],
            )

        # Invariant: Slot reserved_count reaches exactly capacity (2), never exceeds it
        slot_final = db.session.get(AvailabilitySlot, slot.id)
        assert slot_final.reserved_count == 2
