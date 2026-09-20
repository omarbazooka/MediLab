"""Unit tests for CustomerContextService and customer history boundaries."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest
from flask import Flask

from app.extensions import db
from app.models.booking import Booking, BookingItem
from app.models.branch import AvailabilitySlot, Branch
from app.models.customer import Customer
from app.models.test import LabTest, TestCategory
from app.services.customer_context_service import CustomerContextService


@pytest.fixture
def setup_customer_data(app: Flask) -> tuple[int, int]:
    """Create two isolated customers with different bookings."""
    with app.app_context():
        db.create_all()
        # Setup category and test
        cat = TestCategory(name="Hematology", slug="hematology", active=True)
        db.session.add(cat)
        db.session.flush()

        test1 = LabTest(
            category_id=cat.id,
            code="CBC",
            name="Complete Blood Count",
            short_description="Blood health",
            sample_type="Blood",
            price=Decimal("250.00"),
            result_turnaround_text="4 hours",
            active=True,
        )
        test2 = LabTest(
            category_id=cat.id,
            code="TSH",
            name="Thyroid Hormone",
            short_description="Thyroid function",
            sample_type="Serum",
            price=Decimal("220.00"),
            result_turnaround_text="24 hours",
            active=True,
        )
        db.session.add_all([test1, test2])

        branch = Branch(
            name="Dokki Branch",
            address="Dokki",
            phone="+20233371234",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        slot1 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 9, 20),
            time=time(10, 0),
            capacity=5,
            reserved_count=1,
            active=True,
        )
        slot2 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 9, 22),
            time=time(14, 0),
            capacity=5,
            reserved_count=1,
            active=True,
        )
        db.session.add_all([slot1, slot2])
        db.session.flush()

        # Customer A
        cust_a = Customer(name="Ahmed Zaki", phone="+201000000001", email="ahmed@example.com")
        # Customer B
        cust_b = Customer(name="Mona Youssef", phone="+201000000002", email="mona@example.com")
        db.session.add_all([cust_a, cust_b])
        db.session.flush()

        # Booking for Customer A
        bk_a = Booking(
            booking_reference="MED-BK-AAAAA1",
            customer_id=cust_a.id,
            availability_slot_id=slot1.id,
            visit_type="BRANCH",
            branch_id=branch.id,
            scheduled_date=date(2026, 9, 20),
            scheduled_time=time(10, 0),
            status="CONFIRMED",
            idempotency_key="idemp-a-1",
        )
        db.session.add(bk_a)
        db.session.flush()
        item_a = BookingItem(
            booking_id=bk_a.id,
            test_id=test1.id,
            unit_price_snapshot=Decimal("250.00"),
        )
        db.session.add(item_a)

        # Booking for Customer B
        bk_b = Booking(
            booking_reference="MED-BK-BBBBB2",
            customer_id=cust_b.id,
            availability_slot_id=slot2.id,
            visit_type="BRANCH",
            branch_id=branch.id,
            scheduled_date=date(2026, 9, 22),
            scheduled_time=time(14, 0),
            status="CANCELLED",
            idempotency_key="idemp-b-2",
        )
        db.session.add(bk_b)
        db.session.flush()
        item_b = BookingItem(
            booking_id=bk_b.id,
            test_id=test2.id,
            unit_price_snapshot=Decimal("220.00"),
        )
        db.session.add(item_b)
        db.session.commit()

        return cust_a.id, cust_b.id


def test_customer_context_none_when_no_customer(app: Flask) -> None:
    """If customer_id is None, no customer context is loaded."""
    with app.app_context():
        service = CustomerContextService()
        result = service.get_customer_context(None)
        assert result is None


def test_customer_isolation_and_facts(app: Flask, setup_customer_data: tuple[int, int]) -> None:
    """Ensure customer A receives strictly their own history, never customer B's data."""
    cust_a_id, cust_b_id = setup_customer_data

    with app.app_context():
        service = CustomerContextService()

        ctx_a = service.get_customer_context(cust_a_id)
        assert ctx_a is not None
        assert ctx_a["customer_name"] == "Ahmed Zaki"
        assert len(ctx_a["recent_bookings"]) == 1
        assert ctx_a["recent_bookings"][0]["booking_reference"] == "MED-BK-AAAAA1"
        assert "Complete Blood Count" in ctx_a["recent_bookings"][0]["items"]
        assert ctx_a["has_active_booking"] is True
        assert ctx_a["has_cancellations"] is False

        ctx_b = service.get_customer_context(cust_b_id)
        assert ctx_b is not None
        assert ctx_b["customer_name"] == "Mona Youssef"
        assert len(ctx_b["recent_bookings"]) == 1
        assert ctx_b["recent_bookings"][0]["booking_reference"] == "MED-BK-BBBBB2"
        assert "Thyroid Hormone" in ctx_b["recent_bookings"][0]["items"]
        assert ctx_b["has_cancellations"] is True

        # Ensure complete isolation
        assert "MED-BK-BBBBB2" not in str(ctx_a)
        assert "MED-BK-AAAAA1" not in str(ctx_b)
