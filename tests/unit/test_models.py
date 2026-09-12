"""Unit tests for Phase 1 SQLAlchemy 2.x domain models."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from app.extensions import db
from app.models.booking import Booking, BookingItem
from app.models.branch import AvailabilitySlot
from app.models.customer import Customer
from app.models.home_visit import HomeVisit
from app.models.knowledge import KnowledgeDocument


def test_all_15_models_registered(app) -> None:
    """Verify that all 15 core domain models are registered in metadata."""
    expected_tables = {
        "test_categories",
        "lab_tests",
        "packages",
        "package_tests",
        "branches",
        "availability_slots",
        "customers",
        "bookings",
        "booking_items",
        "home_visits",
        "knowledge_documents",
        "knowledge_chunks",
        "conversation_sessions",
        "chat_messages",
        "search_snapshots",
    }
    with app.app_context():
        metadata_tables = set(db.metadata.tables.keys())
        assert expected_tables.issubset(metadata_tables)
        assert len(expected_tables) == 15


def test_availability_slot_is_available_property(app) -> None:
    """Verify AvailabilitySlot.is_available computation."""
    with app.app_context():
        slot = AvailabilitySlot(
            visit_type="HOME",
            date=date(2026, 9, 15),
            time=time(10, 0),
            capacity=3,
            reserved_count=1,
            active=True,
        )
        assert slot.is_available is True

        slot.reserved_count = 3
        assert slot.is_available is False

        slot.reserved_count = 1
        slot.active = False
        assert slot.is_available is False


def test_booking_total_price_property(app) -> None:
    """Verify Booking.total_price aggregates item unit prices."""
    with app.app_context():
        booking = Booking(
            booking_reference="MLB-20260915-TEST",
            customer_id=1,
            availability_slot_id=1,
            visit_type="BRANCH",
            scheduled_date=date(2026, 9, 15),
            scheduled_time=time(9, 0),
            status="CONFIRMED",
            idempotency_key="key-test-1",
        )
        item1 = BookingItem(unit_price_snapshot=Decimal("250.00"))
        item2 = BookingItem(unit_price_snapshot=Decimal("380.50"))
        booking.items.extend([item1, item2])

        assert booking.total_price == Decimal("630.50")


def test_knowledge_document_defaults(app) -> None:
    """Verify KnowledgeDocument default status and version."""
    with app.app_context():
        assert KnowledgeDocument.index_status.default.arg == "PENDING"
        assert KnowledgeDocument.version.default.arg == 1
        assert KnowledgeDocument.active.default.arg is True


def test_home_visit_bounded_status(app) -> None:
    """Verify HomeVisit can be instantiated with valid bounded status."""
    with app.app_context():
        for valid_status in [
            "REQUESTED",
            "SCHEDULED",
            "DISPATCHED",
            "SAMPLE_COLLECTED",
            "CANCELLED",
        ]:
            hv = HomeVisit(
                booking_id=1,
                address="123 Street",
                area="Nasr City",
                status=valid_status,
            )
            assert hv.status == valid_status


def test_customer_model_phone_field(app) -> None:
    """Verify Customer model phone field configuration."""
    with app.app_context():
        customer = Customer(name="Ahmed Hassan", phone="+201001234567")
        assert customer.name == "Ahmed Hassan"
        assert customer.phone == "+201001234567"
        assert customer.email is None
