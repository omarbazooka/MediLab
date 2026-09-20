"""Graph integration tests running full multi-turn conversational flows through MediLabAgent."""

from __future__ import annotations

from decimal import Decimal

import pytest
from flask import Flask

from app.agent.graph import MediLabAgent
from app.agent.llm.factory import set_override_llm_provider
from app.agent.llm.fake import FakeLLMProvider
from app.extensions import db
from app.models.booking import Booking, BookingItem
from app.models.branch import AvailabilitySlot, Branch
from app.models.conversation import ChatMessage, ConversationSession
from app.models.customer import Customer
from app.models.home_visit import HomeVisit
from app.models.package import Package, PackageTest
from app.models.snapshot import SearchSnapshot
from app.models.test import LabTest, TestCategory

pytestmark = pytest.mark.postgres


@pytest.fixture
def clean_graph_db(postgres_app: Flask):
    """Seed catalog tests, packages, and clean conversations on local PostgreSQL."""
    with postgres_app.app_context():
        db.session.rollback()
        db.session.execute(ChatMessage.__table__.delete())
        db.session.execute(SearchSnapshot.__table__.delete())
        db.session.execute(ConversationSession.__table__.delete())
        db.session.execute(BookingItem.__table__.delete())
        db.session.execute(HomeVisit.__table__.delete())
        db.session.execute(Booking.__table__.delete())
        db.session.execute(AvailabilitySlot.__table__.delete())
        db.session.execute(Branch.__table__.delete())
        db.session.execute(PackageTest.__table__.delete())
        db.session.execute(Package.__table__.delete())
        db.session.execute(LabTest.__table__.delete())
        db.session.execute(TestCategory.__table__.delete())
        db.session.execute(Customer.__table__.delete())
        db.session.commit()

        # Seed categories
        cat_hem = TestCategory(name="Hematology", slug="hematology", active=True)
        cat_chem = TestCategory(name="Clinical Chemistry", slug="clinical-chemistry", active=True)
        cat_endo = TestCategory(name="Endocrinology", slug="endocrinology", active=True)
        db.session.add_all([cat_hem, cat_chem, cat_endo])
        db.session.flush()

        # Seed LabTests
        cbc = LabTest(
            category_id=cat_hem.id,
            code="CBC",
            name="Complete Blood Count (CBC)",
            short_description="Measures red and white blood cells.",
            sample_type="Whole Blood (EDTA)",
            price=Decimal("250.00"),
            result_turnaround_text="Same Day (4 hours)",
            active=True,
        )
        lipid = LabTest(
            category_id=cat_chem.id,
            code="LIPID",
            name="Lipid Profile Panel",
            short_description="Measures total cholesterol and triglycerides.",
            sample_type="Serum (10-12 hr fasting)",
            price=Decimal("320.00"),
            result_turnaround_text="Same Day (4 hours)",
            active=True,
        )
        tsh = LabTest(
            category_id=cat_endo.id,
            code="TSH",
            name="Thyroid Stimulating Hormone (TSH)",
            short_description="TSH is a blood test that measures thyroid-stimulating hormone.",
            sample_type="Serum",
            price=Decimal("220.00"),
            result_turnaround_text="24 Hours",
            active=True,
        )
        db.session.add_all([cbc, lipid, tsh])
        db.session.flush()

        # Seed package
        vitality = Package(
            name="Vitality & Wellness Panel",
            description="Specialized panel assessing energy and thyroid regulation.",
            price=Decimal("980.00"),
            active=True,
        )
        db.session.add(vitality)
        db.session.flush()
        db.session.add(PackageTest(package_id=vitality.id, test_id=tsh.id))
        db.session.commit()

        yield postgres_app

    set_override_llm_provider(None)


def test_graph_flow_1_cbc_price_inquiry(clean_graph_db: Flask) -> None:
    """Flow 1: 'How much does CBC cost?' -> Structured branch -> real SQL test -> natural response."""
    with clean_graph_db.app_context():
        set_override_llm_provider(FakeLLMProvider())
        agent = MediLabAgent()

        result = agent.run_turn("sess-f1", "How much does CBC cost?")

        assert result["session_id"] == "sess-f1"
        assert result["is_safe"] is True
        assert result["response_goal"] == "ANSWER"
        assert "structured_data_node" in result["route_trace"]
        assert "250.00 EGP" in result["response"]
        assert "CBC" in result["response"]


def test_graph_flow_2_lipid_fasting_inquiry(clean_graph_db: Flask) -> None:
    """Flow 2: 'Can I drink water before a fasting lipid test?' -> RAG branch -> preparation guidance."""
    with clean_graph_db.app_context():
        set_override_llm_provider(FakeLLMProvider())
        agent = MediLabAgent()

        result = agent.run_turn("sess-f2", "Can I drink water before a fasting lipid test?")

        assert result["is_safe"] is True
        assert "rag_node" in result["route_trace"]
        assert result["response_goal"] in {"ANSWER", "NO_KNOWLEDGE"}


def test_graph_flow_3_combined_tsh_definition_price_fasting(clean_graph_db: Flask) -> None:
    """Flow 3: 'What is TSH, how much is it, and do I need to fast?' -> Combined read -> SQL + RAG."""
    with clean_graph_db.app_context():
        set_override_llm_provider(FakeLLMProvider())
        agent = MediLabAgent()

        result = agent.run_turn("sess-f3", "What is TSH, how much is it, and do I need to fast?")

        assert result["is_safe"] is True
        assert "combined_read_node" in result["route_trace"]
        assert "220.00 EGP" in result["response"]
        assert "TSH" in result["response"]


def test_graph_flow_4_and_5_thyroid_clarification_and_resolution(clean_graph_db: Flask) -> None:
    """Flow 4 & 5: Turn 1 ambiguous inquiry -> clarification turn -> Turn 2 'The full one' -> resolved."""
    with clean_graph_db.app_context():
        set_override_llm_provider(FakeLLMProvider())
        agent = MediLabAgent()

        # Turn 1: 'I want a thyroid test'
        t1 = agent.run_turn("sess-f4", "I want a thyroid test")

        assert t1["response_goal"] == "CLARIFY"
        assert t1["pending_clarification"] is not None
        assert t1["pending_clarification"]["target"] == "test_selection"

        # Turn 2: 'The full one'
        t2 = agent.run_turn("sess-f4", "The full one")

        assert t2["response_goal"] == "ANSWER"
        assert t2["pending_clarification"] is None
        assert t2["selected_package_id"] is not None
        assert "Vitality & Wellness Panel" in t2["response"]


def test_graph_flow_6_clinical_safety_boundary(clean_graph_db: Flask) -> None:
    """Flow 6: 'I have severe dizziness, what test should I take?' -> Clinical safety -> safe boundary."""
    with clean_graph_db.app_context():
        set_override_llm_provider(FakeLLMProvider())
        agent = MediLabAgent()

        result = agent.run_turn("sess-f6", "I have severe dizziness, what test should I take?")

        assert result["is_safe"] is False
        assert result["response_goal"] == "SAFE_BOUNDARY"
        assert (
            "qualified healthcare professional" in result["response"]
            or "طبيب" in result["response"]
        )


def test_graph_flow_7_action_boundary_no_fake_booking(clean_graph_db: Flask) -> None:
    """Flow 7: 'Please book me a home visit for tomorrow.' -> Action boundary routes to business actions.

    Phase 4 requirements:
    - Routes to action_boundary_node
    - Creates and persists pending_action in state and database session
    - Status is NEEDS_DATA because required fields (address/area/test) are missing
    - Asks only for missing information
    - ZERO Booking/HomeVisit rows created before explicit confirmation
    - No fake booking claim made
    """
    with clean_graph_db.app_context():
        set_override_llm_provider(FakeLLMProvider())
        agent = MediLabAgent()

        result = agent.run_turn("sess-f7", "Please book me a home visit for tomorrow.")

        # 1. Safety and routing invariants
        assert result["is_safe"] is True
        assert "action_boundary_node" in result["route_trace"]
        assert result["response_goal"] == "ANSWER"

        # 2. Action state & pending_action collection
        action_res = result.get("action_result")
        assert action_res is not None
        assert action_res["action_type"] == "CREATE_HOME_VISIT"
        assert action_res["status"] == "NEEDS_DATA"
        assert action_res["committed"] is False
        assert "address" in action_res["missing_fields"] or "area" in action_res["missing_fields"]

        # 3. Pending action persisted in return state
        pending = result.get("pending_action")
        assert pending is not None
        assert pending["action_type"] == "CREATE_HOME_VISIT"
        assert pending["visit_type"] == "HOME"
        assert len(pending["missing_fields"]) > 0

        # 4. Zero DB mutations prior to explicit confirmation
        assert db.session.query(Booking).count() == 0
        assert db.session.query(HomeVisit).count() == 0

        # 5. Durable persistence in ConversationSession
        session_rec = db.session.query(ConversationSession).filter_by(session_id="sess-f7").first()
        assert session_rec is not None
        assert session_rec.pending_action is not None
        assert session_rec.pending_action.get("action_type") == "CREATE_HOME_VISIT"

        # 6. Safety boundary preserved: No fake booking confirmation claim
        assert "booking is confirmed" not in result["response"].lower()
        assert "تم تأكيد حجزك" not in result["response"]
        # Asks for missing information
        assert any(
            field in result["response"].lower()
            for field in ["name", "phone", "address", "area", "detail"]
        ) or any(w in result["response"] for w in ["الاسم", "الهاتف", "عنوان", "المنطقة", "بيانات"])
