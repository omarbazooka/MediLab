"""Unit tests for Phase 4 multi-turn pending action conversation flow, field merging, and confirmation gating.

Covers criteria 30-35:
30) pending_action persists across turns via database session
31) fields merge across turns (date/time/branch/name/phone)
32) asks only missing fields
33) explicit confirmation required before mutating database
34) successful action clears/completes pending_action
35) session isolation preserved
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from flask import Flask

from app.agent.graph import MediLabAgent
from app.agent.llm.factory import set_override_llm_provider
from app.agent.llm.fake import FakeLLMProvider
from app.agent.pending_action import parse_date_and_time
from app.extensions import db
from app.models.booking import Booking
from app.models.branch import AvailabilitySlot, Branch
from app.models.conversation import ConversationSession
from app.models.test import LabTest, TestCategory


@pytest.fixture
def conversation_catalog(app: Flask):
    """Seed branch, slots, and test for end-to-end LangGraph conversational testing."""
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

        branch_nasr = Branch(
            name="Nasr City Branch",
            address="45 Abbas El Akkad, Nasr City, Cairo",
            phone="+20224012345",
            opening_hours_json={"regular": "09:00 - 19:00"},
            active=True,
        )
        db.session.add(branch_nasr)
        db.session.flush()

        # Keep the seeded slot aligned with the agent's canonical interpretation
        # of the relative phrase used by these deterministic evaluation flows.
        target_date, _ = parse_date_and_time("tomorrow", {})
        assert target_date is not None
        from datetime import time

        slot_1600 = AvailabilitySlot(
            branch_id=branch_nasr.id,
            visit_type="BRANCH",
            date=target_date,
            time=time(16, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        slot_1630 = AvailabilitySlot(
            branch_id=branch_nasr.id,
            visit_type="BRANCH",
            date=target_date,
            time=time(16, 30),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        # Home slot
        slot_home = AvailabilitySlot(
            branch_id=None,
            visit_type="HOME",
            date=target_date,
            time=time(10, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )

        db.session.add_all([slot_1600, slot_1630, slot_home])
        db.session.commit()

        yield {
            "test_cbc": test_cbc,
            "branch_nasr": branch_nasr,
            "target_date": target_date,
            "slot_1600": slot_1600,
            "slot_1630": slot_1630,
            "slot_home": slot_home,
        }


def test_rule_30_31_32_33_34_multi_turn_branch_booking_flow(
    app: Flask, conversation_catalog: dict
) -> None:
    """Criteria 30-34: Multi-turn flow persists pending_action, merges fields, asks only missing, requires explicit confirmation, and clears on success."""
    with app.app_context():
        fake_llm = FakeLLMProvider()
        set_override_llm_provider(fake_llm)
        agent = MediLabAgent()

        session_id = "sess-flow-branch-001"
        initial_bookings = db.session.query(Booking).count()

        # ------------------------------------------------------------------
        # Turn 1: User specifies test, branch, and time, but NO name or phone
        # ------------------------------------------------------------------
        res_turn1 = agent.run_turn(
            session_id=session_id,
            message="I want to book CBC at Nasr City tomorrow at 4 PM",
        )

        # Invariant 30 & 32: Pending action persisted, needs missing data
        pending_1 = res_turn1.get("pending_action")
        assert pending_1 is not None
        assert pending_1["action_type"] == "CREATE_BRANCH_BOOKING"
        assert pending_1["branch_id"] == conversation_catalog["branch_nasr"].id
        assert pending_1["scheduled_time"] == "16:00"
        assert "customer_name" in pending_1["missing_fields"]
        assert "customer_phone" in pending_1["missing_fields"]

        # Invariant 33: ZERO database rows created
        assert db.session.query(Booking).count() == initial_bookings

        # Durable check: verified in DB ConversationSession
        session_row = db.session.query(ConversationSession).filter_by(session_id=session_id).one()
        assert session_row.pending_action is not None
        assert session_row.pending_action["action_type"] == "CREATE_BRANCH_BOOKING"

        # ------------------------------------------------------------------
        # Turn 2: User provides missing name and phone
        # ------------------------------------------------------------------
        res_turn2 = agent.run_turn(
            session_id=session_id,
            message="My name is Omar Ahmed and phone is 01012345678",
        )

        # Invariant 31: Fields merged safely across turns
        pending_2 = res_turn2.get("pending_action")
        assert pending_2 is not None
        assert pending_2["customer_name"] == "Omar Ahmed"
        assert "01012345678" in pending_2["customer_phone"]
        assert len(pending_2["missing_fields"]) == 0

        # Invariant 33: Still NO insert prior to explicit confirmation
        assert db.session.query(Booking).count() == initial_bookings
        action_res_2 = res_turn2.get("action_result")
        assert action_res_2["status"] == "AWAITING_CONFIRMATION"
        assert action_res_2["committed"] is False
        assert "Omar Ahmed" in res_turn2["response"] or "Omar Ahmed" in action_res_2["message"]

        # ------------------------------------------------------------------
        # Turn 3: User explicitly confirms
        # ------------------------------------------------------------------
        res_turn3 = agent.run_turn(
            session_id=session_id,
            message="Yes, please confirm the booking",
        )

        # Invariant 34: Action executed, committed to DB, real reference returned
        action_res_3 = res_turn3.get("action_result")
        assert action_res_3 is not None
        assert action_res_3["status"] == "EXECUTED"
        assert action_res_3["committed"] is True
        assert action_res_3["success"] is True
        booking_ref = action_res_3["booking_reference"]
        assert booking_ref.startswith("MLB-")

        # Database has exactly one new booking
        assert db.session.query(Booking).count() == initial_bookings + 1
        booking_row = db.session.query(Booking).filter_by(booking_reference=booking_ref).one()
        assert booking_row.customer.name == "Omar Ahmed"
        assert booking_row.status == "CONFIRMED"

        # Invariant 34: Pending action cleared or completed
        session_row_final = (
            db.session.query(ConversationSession).filter_by(session_id=session_id).one()
        )
        assert session_row_final.pending_action is None


def test_rule_35_session_isolation_preserved(app: Flask, conversation_catalog: dict) -> None:
    """Criteria 35: Actions and pending states in Session A do NOT leak or affect Session B."""
    with app.app_context():
        fake_llm = FakeLLMProvider()
        set_override_llm_provider(fake_llm)
        agent = MediLabAgent()

        session_a = "sess-isolation-alpha"
        session_b = "sess-isolation-beta"

        # Session A starts booking CBC
        res_a1 = agent.run_turn(
            session_id=session_a,
            message="I want to book CBC at Nasr City tomorrow at 4 PM",
        )
        assert res_a1.get("pending_action") is not None
        assert res_a1["pending_action"]["test_id"] == conversation_catalog["test_cbc"].id

        # Session B starts completely unrelated conversation
        res_b1 = agent.run_turn(
            session_id=session_b,
            message="What are your operating hours?",
        )

        # Session B must NOT have Session A's pending action
        assert res_b1.get("pending_action") is None

        # Verify in DB
        session_a_row = db.session.query(ConversationSession).filter_by(session_id=session_a).one()
        session_b_row = db.session.query(ConversationSession).filter_by(session_id=session_b).one()
        assert session_a_row.pending_action is not None
        assert session_b_row.pending_action is None


def test_cancel_booking_multi_turn_flow(app: Flask, conversation_catalog: dict) -> None:
    """Multi-turn cancellation flow asks for confirmation before executing cancellation."""
    with app.app_context():
        fake_llm = FakeLLMProvider()
        set_override_llm_provider(fake_llm)
        agent = MediLabAgent()

        # Create a real booking first
        from app.services.booking_service import BookingService

        service = BookingService()
        booking = service.create_branch_booking(
            customer_name="Tamer Hosny",
            customer_phone="+201077665544",
            branch_id=conversation_catalog["branch_nasr"].id,
            slot_id=conversation_catalog["slot_1630"].id,
            idempotency_key="idemp-cancel-flow-1",
            test_ids=[conversation_catalog["test_cbc"].id],
        )
        ref = booking.booking_reference
        assert booking.status == "CONFIRMED"

        session_id = "sess-cancel-flow-001"

        # Turn 1: User asks to cancel booking
        res_1 = agent.run_turn(
            session_id=session_id,
            message=f"Please cancel my booking {ref}",
        )
        action_res_1 = res_1.get("action_result")
        assert action_res_1 is not None
        assert action_res_1["status"] == "AWAITING_CONFIRMATION"
        assert action_res_1["committed"] is False
        # Booking still CONFIRMED
        assert db.session.get(Booking, booking.id).status == "CONFIRMED"

        # Turn 2: User confirms
        res_2 = agent.run_turn(
            session_id=session_id,
            message="Yes, please confirm cancellation",
        )
        action_res_2 = res_2.get("action_result")
        assert action_res_2 is not None
        assert action_res_2["status"] == "CANCELLED"
        assert action_res_2["committed"] is True

        # Invariant: Booking is now CANCELLED in DB
        reloaded_booking = db.session.get(Booking, booking.id)
        assert reloaded_booking.status == "CANCELLED"
        assert reloaded_booking.cancelled_at is not None


def test_home_visit_multi_turn_flow(app: Flask, conversation_catalog: dict) -> None:
    """Multi-turn home visit collection asks for address/area/phone, presents summary, and commits on confirm."""
    with app.app_context():
        fake_llm = FakeLLMProvider()
        set_override_llm_provider(fake_llm)
        agent = MediLabAgent()

        session_id = "sess-home-flow-001"
        from app.models.home_visit import HomeVisit

        initial_home_visits = db.session.query(HomeVisit).count()

        # Turn 1: "I want to book a home visit for CBC tomorrow at 10 AM"
        res_1 = agent.run_turn(
            session_id=session_id,
            message="I want to book a home visit for CBC tomorrow at 10 AM",
        )
        pending_1 = res_1.get("pending_action")
        assert pending_1 is not None
        assert pending_1["action_type"] == "CREATE_HOME_VISIT"
        assert pending_1["visit_type"] == "HOME"
        assert "address" in pending_1["missing_fields"]
        assert "customer_name" in pending_1["missing_fields"]
        assert db.session.query(HomeVisit).count() == initial_home_visits

        # Turn 2: User provides address and contact details
        res_2 = agent.run_turn(
            session_id=session_id,
            message="My name is Sarah Nour, phone 01233445566, address 22 Pyramids St, Giza",
        )
        action_res_2 = res_2.get("action_result")
        assert action_res_2 is not None
        assert action_res_2["status"] == "AWAITING_CONFIRMATION"
        assert action_res_2["committed"] is False
        assert db.session.query(HomeVisit).count() == initial_home_visits

        # Turn 3: User confirms
        res_3 = agent.run_turn(
            session_id=session_id,
            message="Confirm",
        )
        action_res_3 = res_3.get("action_result")
        assert action_res_3 is not None
        assert action_res_3["status"] == "EXECUTED"
        assert action_res_3["committed"] is True
        assert db.session.query(HomeVisit).count() == initial_home_visits + 1
