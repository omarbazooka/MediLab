"""Unit tests for Phase 1 business services and domain logic."""

from __future__ import annotations

import re
from datetime import date, time
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.branch import AvailabilitySlot, Branch
from app.models.package import Package, PackageTest
from app.models.test import LabTest, TestCategory
from app.services.booking_service import (
    BookingNotFoundError,
    BookingService,
    BookingValidationError,
)
from app.services.branch_service import BranchService
from app.services.package_service import PackageService
from app.services.test_service import TestService


@pytest.fixture
def catalog_data(app):
    """Seed lightweight in-memory catalog data for fast unit testing."""
    with app.app_context():
        db.create_all()

        cat1 = TestCategory(name="Hematology", slug="hematology", active=True)
        cat2 = TestCategory(name="Biochemistry", slug="biochemistry", active=True)
        db.session.add_all([cat1, cat2])
        db.session.flush()

        test1 = LabTest(
            code="CBC",
            name="Complete Blood Count",
            category_id=cat1.id,
            short_description="Blood health screen",
            sample_type="Whole Blood",
            price=Decimal("250.00"),
            result_turnaround_text="4 hours",
            active=True,
        )
        test2 = LabTest(
            code="FERRITIN",
            name="Serum Ferritin",
            category_id=cat1.id,
            short_description="Iron store check",
            sample_type="Serum",
            price=Decimal("280.00"),
            result_turnaround_text="24 hours",
            active=True,
        )
        test3 = LabTest(
            code="FBS",
            name="Fasting Blood Sugar",
            category_id=cat2.id,
            short_description="Glucose level",
            sample_type="Plasma",
            price=Decimal("90.00"),
            result_turnaround_text="2 hours",
            active=True,
        )
        test_archived = LabTest(
            code="OLD_TEST",
            name="Archived Diagnostic",
            category_id=cat1.id,
            short_description="Legacy",
            sample_type="Serum",
            price=Decimal("120.00"),
            result_turnaround_text="N/A",
            active=False,
        )
        db.session.add_all([test1, test2, test3, test_archived])
        db.session.flush()

        pkg = Package(
            name="Wellness Package",
            description="Basic screening",
            price=Decimal("300.00"),
            active=True,
        )
        db.session.add(pkg)
        db.session.flush()

        db.session.add(PackageTest(package_id=pkg.id, test_id=test1.id))
        db.session.add(PackageTest(package_id=pkg.id, test_id=test3.id))

        branch1 = Branch(
            name="Downtown Branch",
            address="100 Main St",
            phone="+2020000001",
            opening_hours_json={},
            active=True,
        )
        branch2 = Branch(
            name="Suburban Branch",
            address="200 West St",
            phone="+2020000002",
            opening_hours_json={},
            active=False,
        )
        db.session.add_all([branch1, branch2])
        db.session.flush()

        # Slot today + 1 day
        slot1 = AvailabilitySlot(
            branch_id=branch1.id,
            visit_type="BRANCH",
            date=date(2026, 9, 21),
            time=time(9, 0),
            capacity=3,
            reserved_count=0,
            active=True,
        )
        # Full slot
        slot2 = AvailabilitySlot(
            branch_id=branch1.id,
            visit_type="BRANCH",
            date=date(2026, 9, 21),
            time=time(11, 0),
            capacity=2,
            reserved_count=2,
            active=True,
        )
        # Home slot
        slot3 = AvailabilitySlot(
            branch_id=None,
            visit_type="HOME",
            date=date(2026, 9, 22),
            time=time(10, 0),
            capacity=4,
            reserved_count=1,
            active=True,
        )
        # Past slot
        slot_past = AvailabilitySlot(
            branch_id=branch1.id,
            visit_type="BRANCH",
            date=date(2026, 1, 1),
            time=time(9, 0),
            capacity=5,
            reserved_count=0,
            active=True,
        )
        db.session.add_all([slot1, slot2, slot3, slot_past])
        db.session.commit()

        yield {
            "cat1": cat1,
            "cat2": cat2,
            "test1": test1,
            "test2": test2,
            "test3": test3,
            "test_archived": test_archived,
            "pkg": pkg,
            "branch1": branch1,
            "slot1": slot1,
            "slot2": slot2,
            "slot3": slot3,
        }
        db.session.rollback()


# ==============================================================================
# TestService Unit Tests
# ==============================================================================


def test_test_service_search_exact_code(catalog_data) -> None:
    """Verify search by exact test code."""
    service = TestService()
    results = service.search_tests(query="CBC")
    assert len(results) == 1
    assert results[0].code == "CBC"


def test_test_service_search_partial_name(catalog_data) -> None:
    """Verify search by partial name matching."""
    service = TestService()
    results = service.search_tests(query="Blood")
    assert any(t.code == "CBC" for t in results)
    assert any(t.code == "FBS" for t in results)


def test_test_service_search_by_category(catalog_data) -> None:
    """Verify search filtered by category slug and category ID."""
    service = TestService()
    results_slug = service.search_tests(category_slug="hematology")
    assert len(results_slug) == 2
    assert all(t.category_id == catalog_data["cat1"].id for t in results_slug)

    results_id = service.search_tests(category_id=catalog_data["cat2"].id)
    assert len(results_id) == 1
    assert results_id[0].code == "FBS"


def test_test_service_inactive_exclusion(catalog_data) -> None:
    """Verify inactive tests are excluded by default and included with active_only=False."""
    service = TestService()
    active_results = service.search_tests(active_only=True)
    assert not any(t.code == "OLD_TEST" for t in active_results)

    all_results = service.search_tests(active_only=False)
    assert any(t.code == "OLD_TEST" for t in all_results)


def test_test_service_price_range(catalog_data) -> None:
    """Verify search within price bounds."""
    service = TestService()
    results = service.search_tests(min_price=Decimal("100.00"), max_price=Decimal("260.00"))
    assert len(results) == 1
    assert results[0].code == "CBC"


def test_test_service_empty_result(catalog_data) -> None:
    """Verify search returns empty list when query does not match."""
    service = TestService()
    assert service.search_tests(query="NONEXISTENT_XYZ") == []
    assert service.get_test_by_code("UNKNOWN_CODE") is None


def test_test_service_get_test_by_code_and_id(catalog_data) -> None:
    """Verify retrieval by unique code and primary key ID."""
    service = TestService()
    test_by_code = service.get_test_by_code("FERRITIN")
    assert test_by_code is not None
    assert test_by_code.name == "Serum Ferritin"

    test_by_id = service.get_test_details(catalog_data["test1"].id)
    assert test_by_id is not None
    assert test_by_id.code == "CBC"


# ==============================================================================
# PackageService Unit Tests
# ==============================================================================


def test_package_service_search_and_details(catalog_data) -> None:
    """Verify package search, details retrieval, and included tests."""
    service = PackageService()
    results = service.search_packages(query="Wellness")
    assert len(results) == 1
    assert results[0].name == "Wellness Package"

    pkg_details = service.get_package_details(catalog_data["pkg"].id)
    assert pkg_details is not None
    assert len(pkg_details.tests) == 2
    included_codes = {t.code for t in pkg_details.tests}
    assert included_codes == {"CBC", "FBS"}

    pkg_by_name = service.get_package_by_name("Wellness Package")
    assert pkg_by_name is not None
    assert pkg_by_name.id == catalog_data["pkg"].id


# ==============================================================================
# BranchService Unit Tests
# ==============================================================================


def test_branch_service_list_and_details(catalog_data) -> None:
    """Verify listing active branches and fetching branch details."""
    service = BranchService()
    active_branches = service.list_active_branches()
    assert len(active_branches) == 1
    assert active_branches[0].name == "Downtown Branch"

    branch = service.get_branch_details(catalog_data["branch1"].id)
    assert branch is not None
    assert branch.address == "100 Main St"


def test_branch_service_find_available_slots_filters(catalog_data) -> None:
    """Verify slot availability filtering by branch, visit_type, and capacity."""
    service = BranchService()

    # Slot with available capacity returned, full slot (slot2) excluded
    branch_slots = service.find_available_slots(
        branch_id=catalog_data["branch1"].id,
        visit_type="BRANCH",
        target_date=date(2026, 9, 21),
    )
    assert len(branch_slots) == 1
    assert branch_slots[0].time == time(9, 0)
    assert branch_slots[0].reserved_count < branch_slots[0].capacity

    # Home slots
    home_slots = service.find_available_slots(visit_type="HOME", target_date=date(2026, 9, 22))
    assert len(home_slots) == 1
    assert home_slots[0].visit_type == "HOME"


def test_branch_service_past_slots_excluded_by_default(catalog_data) -> None:
    """Verify slots prior to from_date are excluded unless include_past=True."""
    service = BranchService()
    # Query with from_date after past slot
    future_slots = service.find_available_slots(
        from_date=date(2026, 9, 1),
        include_past=False,
    )
    assert not any(s.date < date(2026, 9, 1) for s in future_slots)

    past_slots = service.find_available_slots(include_past=True)
    assert any(s.date == date(2026, 1, 1) for s in past_slots)


# ==============================================================================
# BookingService Unit Tests (Validation & Logic)
# ==============================================================================


def test_booking_reference_generation_format_and_entropy() -> None:
    """Verify generated booking references conform to MLB-YYYYMMDD-XXXXXXXX (8 hex chars)."""
    ref = BookingService.generate_booking_reference()
    pattern = r"^MLB-\d{8}-[A-Z0-9]{8}$"
    assert re.match(pattern, ref), f"Reference '{ref}' does not match pattern {pattern}"

    # Verify uniqueness across batch
    refs = {BookingService.generate_booking_reference() for _ in range(100)}
    assert len(refs) == 100


def test_booking_service_validation_errors(catalog_data) -> None:
    """Verify BookingService raises BookingValidationError on invalid input payloads."""
    service = BookingService()

    # 1. Missing customer name
    with pytest.raises(BookingValidationError, match="customer_name is required"):
        service.create_booking(
            customer_name="",
            customer_phone="+201000000000",
            slot_id=catalog_data["slot1"].id,
            visit_type="BRANCH",
            idempotency_key="key-val-1",
            branch_id=catalog_data["branch1"].id,
            test_ids=[catalog_data["test1"].id],
        )

    # 2. Missing customer phone
    with pytest.raises(BookingValidationError, match="customer_phone is required"):
        service.create_booking(
            customer_name="Patient Name",
            customer_phone=" ",
            slot_id=catalog_data["slot1"].id,
            visit_type="BRANCH",
            idempotency_key="key-val-2",
            branch_id=catalog_data["branch1"].id,
            test_ids=[catalog_data["test1"].id],
        )

    # 3. Invalid visit_type
    with pytest.raises(BookingValidationError, match="Invalid visit_type"):
        service.create_booking(
            customer_name="Patient Name",
            customer_phone="+201000000000",
            slot_id=catalog_data["slot1"].id,
            visit_type="TELECLINIC",
            idempotency_key="key-val-3",
            branch_id=catalog_data["branch1"].id,
            test_ids=[catalog_data["test1"].id],
        )

    # 4. BRANCH visit without branch_id
    with pytest.raises(BookingValidationError, match="branch_id is required for BRANCH visits"):
        service.create_booking(
            customer_name="Patient Name",
            customer_phone="+201000000000",
            slot_id=catalog_data["slot1"].id,
            visit_type="BRANCH",
            idempotency_key="key-val-4",
            branch_id=None,
            test_ids=[catalog_data["test1"].id],
        )

    # 5. HOME visit without address or area
    with pytest.raises(BookingValidationError, match="address is required for HOME visits"):
        service.create_booking(
            customer_name="Patient Name",
            customer_phone="+201000000000",
            slot_id=catalog_data["slot3"].id,
            visit_type="HOME",
            idempotency_key="key-val-5",
            address="",
            area="Maadi",
            test_ids=[catalog_data["test1"].id],
        )

    # 6. No items selected
    with pytest.raises(
        BookingValidationError, match="At least one test or package must be selected"
    ):
        service.create_booking(
            customer_name="Patient Name",
            customer_phone="+201000000000",
            slot_id=catalog_data["slot1"].id,
            visit_type="BRANCH",
            idempotency_key="key-val-6",
            branch_id=catalog_data["branch1"].id,
            test_ids=[],
            package_ids=[],
        )


def test_cancel_nonexistent_booking_raises_not_found(catalog_data) -> None:
    """Verify cancelling an unrecorded reference raises BookingNotFoundError."""
    service = BookingService()
    with pytest.raises(BookingNotFoundError, match="Booking reference 'MLB-NONEXISTENT' not found"):
        service.cancel_booking("MLB-NONEXISTENT")
