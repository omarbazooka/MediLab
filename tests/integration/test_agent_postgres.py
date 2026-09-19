"""PostgreSQL integration tests for durable conversation state, session isolation, and snapshots."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest
from flask import Flask

from app.agent.context import load_conversation_context
from app.agent.nodes.clarification_node import clarification_node
from app.agent.nodes.persist_context import persist_context
from app.agent.nodes.resolve_pending_context import resolve_pending_context
from app.agent.state import create_initial_state
from app.extensions import db
from app.models.booking import Booking, BookingItem
from app.models.branch import AvailabilitySlot, Branch
from app.models.conversation import ChatMessage, ConversationSession
from app.models.customer import Customer
from app.models.snapshot import SearchSnapshot
from app.models.test import LabTest, TestCategory
from app.repositories.conversation_repository import ConversationRepository

pytestmark = pytest.mark.postgres


@pytest.fixture
def clean_postgres_db(postgres_app: Flask):
    """Ensure clean PostgreSQL tables before each integration test."""
    with postgres_app.app_context():
        # Clear transaction state and clean up test rows safely
        db.session.rollback()
        # Clean conversation and booking test entities
        db.session.execute(ChatMessage.__table__.delete())
        db.session.execute(SearchSnapshot.__table__.delete())
        db.session.execute(ConversationSession.__table__.delete())
        db.session.execute(BookingItem.__table__.delete())
        db.session.execute(Booking.__table__.delete())
        db.session.execute(AvailabilitySlot.__table__.delete())
        db.session.execute(Branch.__table__.delete())
        db.session.execute(Customer.__table__.delete())
        db.session.commit()
        yield postgres_app


def test_postgres_new_and_existing_session_hydration(clean_postgres_db: Flask) -> None:
    """Test creating, persisting, and rehydrating a ConversationSession from PostgreSQL."""
    with clean_postgres_db.app_context():
        repo = ConversationRepository()

        # Create session
        repo.create_session("sess-pg-1", initial_state={"pref": "ar"})
        db.session.commit()

        # Add messages
        repo.add_message("sess-pg-1", "user", "Hello", intent="GREETING")
        repo.add_message("sess-pg-1", "assistant", "Welcome to MediLab!", intent="GREETING")
        db.session.commit()

        # Hydrate via load_conversation_context
        ctx = load_conversation_context("sess-pg-1")

        assert ctx["session_id"] == "sess-pg-1"
        assert len(ctx["recent_messages"]) == 2
        assert ctx["recent_messages"][0]["role"] == "user"
        assert ctx["recent_messages"][0]["content"] == "Hello"
        assert ctx["recent_messages"][1]["role"] == "assistant"
        assert ctx["current_state"] == {"pref": "ar"}


def test_postgres_session_isolation(clean_postgres_db: Flask) -> None:
    """Test that Session A and Session B are completely isolated in PostgreSQL."""
    with clean_postgres_db.app_context():
        repo = ConversationRepository()

        # Session A
        repo.create_session("sess-iso-A")
        repo.add_message("sess-iso-A", "user", "Message from User A")
        db.session.commit()

        # Session B
        repo.create_session("sess-iso-B")
        repo.add_message("sess-iso-B", "user", "Message from User B")
        db.session.commit()

        ctx_a = load_conversation_context("sess-iso-A")
        ctx_b = load_conversation_context("sess-iso-B")

        assert len(ctx_a["recent_messages"]) == 1
        assert ctx_a["recent_messages"][0]["content"] == "Message from User A"

        assert len(ctx_b["recent_messages"]) == 1
        assert ctx_b["recent_messages"][0]["content"] == "Message from User B"

        assert "User B" not in str(ctx_a)
        assert "User A" not in str(ctx_b)


def test_postgres_customer_history_and_isolation(clean_postgres_db: Flask) -> None:
    """Test customer history attachment and customer isolation on PostgreSQL."""
    with clean_postgres_db.app_context():
        # Setup catalog test & branch
        cat = db.session.execute(
            db.select(TestCategory).where(TestCategory.slug == "hematology")
        ).scalar_one_or_none()
        if not cat:
            cat = TestCategory(name="Hematology", slug="hematology", active=True)
            db.session.add(cat)
            db.session.flush()

        test = db.session.execute(
            db.select(LabTest).where(LabTest.code == "CBC")
        ).scalar_one_or_none()
        if not test:
            test = LabTest(
                code="CBC",
                name="Complete Blood Count",
                category_id=cat.id,
                short_description="Blood health",
                sample_type="Blood",
                price=Decimal("250.00"),
                result_turnaround_text="4 hours",
                active=True,
            )
            db.session.add(test)
            db.session.flush()

        branch = Branch(
            name="Dokki Branch",
            address="Dokki",
            phone="+20233371234",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        slot = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 9, 21),
            time=time(11, 0),
            capacity=5,
            reserved_count=1,
            active=True,
        )
        db.session.add(slot)
        db.session.flush()

        # Create Customer 1 & 2
        c1 = Customer(name="Tarek Omar", phone="+201111111111", email="tarek@example.com")
        c2 = Customer(name="Sara Adel", phone="+201222222222", email="sara@example.com")
        db.session.add_all([c1, c2])
        db.session.flush()

        # Create Booking for Customer 1
        bk1 = Booking(
            booking_reference="MED-TEST-BK1",
            customer_id=c1.id,
            availability_slot_id=slot.id,
            visit_type="BRANCH",
            branch_id=branch.id,
            scheduled_date=date(2026, 9, 21),
            scheduled_time=time(11, 0),
            status="CONFIRMED",
            idempotency_key="idemp-pg-c1",
        )
        db.session.add(bk1)
        db.session.flush()
        db.session.add(
            BookingItem(booking_id=bk1.id, test_id=test.id, unit_price_snapshot=Decimal("250.00"))
        )

        # Create Session for Customer 1
        repo = ConversationRepository()
        repo.create_session("sess-c1", customer_id=c1.id)
        # Create Session for Customer 2
        repo.create_session("sess-c2", customer_id=c2.id)
        # Create Session unassociated
        repo.create_session("sess-anon", customer_id=None)
        db.session.commit()

        # 1. Unassociated session has no history
        ctx_anon = load_conversation_context("sess-anon")
        assert ctx_anon["customer_context"] is None

        # 2. Customer 1 has booking
        ctx_c1 = load_conversation_context("sess-c1")
        assert ctx_c1["customer_context"] is not None
        assert ctx_c1["customer_context"]["customer_name"] == "Tarek Omar"
        assert len(ctx_c1["customer_context"]["recent_bookings"]) == 1
        assert (
            ctx_c1["customer_context"]["recent_bookings"][0]["booking_reference"] == "MED-TEST-BK1"
        )

        # 3. Customer 2 has no bookings
        ctx_c2 = load_conversation_context("sess-c2")
        assert ctx_c2["customer_context"] is not None
        assert ctx_c2["customer_context"]["customer_name"] == "Sara Adel"
        assert len(ctx_c2["customer_context"]["recent_bookings"]) == 0

        # Strict isolation check
        assert "MED-TEST-BK1" not in str(ctx_c2)


def test_postgres_search_snapshot_ordinal_resolution(clean_postgres_db: Flask) -> None:
    """Test persisting SearchSnapshot to PostgreSQL and resolving ordinals across turns."""
    with clean_postgres_db.app_context():
        from app.models.package import Package

        pkg = db.session.execute(
            db.select(Package).where(Package.name == "Vitality & Wellness Panel")
        ).scalar_one_or_none()
        if not pkg:
            pkg = Package(
                name="Vitality & Wellness Panel",
                description="Panel",
                price=Decimal("980.00"),
                active=True,
            )
            db.session.add(pkg)
            db.session.flush()

        repo = ConversationRepository()
        repo.create_session("sess-snap-1")
        db.session.commit()

        # Turn 1: Save snapshot with 2 items
        snapshot = repo.save_snapshot(
            session_id="sess-snap-1",
            sequence_no=1,
            query="thyroid",
            criteria={"target": "test_selection"},
            items=[
                {"type": "test", "id": 1, "code": "TSH", "name": "Thyroid Stimulating Hormone"},
                {"type": "package", "id": pkg.id, "name": "Vitality & Wellness Panel"},
            ],
        )
        db.session.commit()

        # Verify active snapshot linked in session
        session = repo.get_session("sess-snap-1")
        assert session.active_snapshot_id == snapshot.id

        # Turn 2: Hydrate context from PostgreSQL
        ctx = load_conversation_context("sess-snap-1")
        assert ctx["active_search_snapshot"] is not None
        assert len(ctx["active_search_snapshot"]["items"]) == 2

        # User says "the second one"
        state = create_initial_state("sess-snap-1", "the second one")
        state["active_search_snapshot"] = ctx["active_search_snapshot"]
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}

        update = resolve_pending_context(state)

        assert update["selected_package_id"] == pkg.id
        assert update["selected_test_id"] is None
        assert update["pending_clarification"] is None

        # Persist resolved turn to DB
        final_state = {
            **state,
            **update,
            "response_goal": "ANSWER",
            "final_response": "You selected Vitality Panel.",
        }
        persist_context(final_state)

        # Verify persisted state in DB
        reloaded = repo.get_session("sess-snap-1")
        assert reloaded.selected_package_id == pkg.id
        assert reloaded.pending_clarification is None


def test_postgres_clarification_persistence_across_turns(clean_postgres_db: Flask) -> None:
    """Test that clarification suspends a turn in PostgreSQL and resumes cleanly on next turn."""
    with clean_postgres_db.app_context():
        repo = ConversationRepository()
        repo.create_session("sess-clarify-loop")
        db.session.commit()

        # Turn 1: Broad query generates clarification and persists
        state_t1 = create_initial_state("sess-clarify-loop", "I want a thyroid test")
        state_t1["needs_clarification"] = True
        state_t1["clarification_target"] = "test_selection"

        t1_update = clarification_node(state_t1)
        merged_t1 = {**state_t1, **t1_update}
        persist_context(merged_t1)

        # Verify DB has pending clarification
        s1 = repo.get_session("sess-clarify-loop")
        assert s1.pending_clarification is not None
        assert s1.pending_clarification["attempts"] == 1
        assert s1.active_snapshot_id is not None

        # Turn 2: Next turn resumes with new graph invocation
        ctx_t2 = load_conversation_context("sess-clarify-loop")
        assert ctx_t2["pending_clarification"] is not None
        assert ctx_t2["active_search_snapshot"] is not None

        # User provides answer: "the full one"
        state_t2 = create_initial_state("sess-clarify-loop", "the full one")
        state_t2["active_search_snapshot"] = ctx_t2["active_search_snapshot"]
        state_t2["pending_clarification"] = ctx_t2["pending_clarification"]

        t2_res = resolve_pending_context(state_t2)
        assert t2_res["pending_clarification"] is None
        assert t2_res["selected_package_id"] is not None

        # Persist turn 2
        merged_t2 = {
            **state_t2,
            **t2_res,
            "response_goal": "ANSWER",
            "final_response": "Details for Vitality Panel",
        }
        persist_context(merged_t2)

        # Verify DB cleared pending clarification and saved selection
        s2 = repo.get_session("sess-clarify-loop")
        assert s2.pending_clarification is None
        assert s2.selected_package_id is not None
