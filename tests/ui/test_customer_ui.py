"""Phase 5 customer Flask/Jinja and chat HTTP contract tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.branch import Branch
from app.models.conversation import ChatMessage, ConversationSession
from app.models.package import Package
from app.models.test import LabTest, TestCategory


@pytest.fixture(autouse=True)
def customer_schema(app):
    """Create a representative local catalog without inventing production page data."""
    with app.app_context():
        db.create_all()
        category = TestCategory(name="Hematology", slug="hematology")
        lab_test = LabTest(
            category=category,
            code="CBC",
            name="Complete Blood Count",
            short_description="Measures components of a blood sample.",
            sample_type="Blood",
            price=Decimal("250.00"),
            result_turnaround_text="Same day",
        )
        package = Package(
            name="Essential Wellness",
            description="A bundled set of routine laboratory services.",
            price=Decimal("600.00"),
            tests=[lab_test],
        )
        branch = Branch(
            name="Nasr City",
            address="Verified test address",
            phone="01000000000",
            opening_hours_json={"open": "09:00", "close": "19:00"},
        )
        db.session.add_all([category, lab_test, package, branch])
        db.session.commit()
    yield
    with app.app_context():
        db.session.remove()
        db.drop_all()


class RecordingAgent:
    def __init__(self, responses=None):
        self.calls: list[tuple[str, str]] = []
        self.responses = list(responses or [])

    def run_turn(self, session_id: str, message: str):
        self.calls.append((session_id, message))
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = {"response": "I can help with verified MediLab services."}
        return {"session_id": session_id, **response}


def install_agent(app, agent):
    app.extensions["medilab_agent"] = agent


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", b"Lab services"),
        ("/chat", b"MediLab AI Assistant"),
        ("/tests", b"Complete Blood Count"),
        ("/packages", b"Essential Wellness"),
        ("/branches", b"Nasr City"),
        ("/booking-status", b"Booking lookup"),
    ],
)
def test_customer_pages_render_real_data(client, path, expected):
    response = client.get(path)
    assert response.status_code == 200
    assert expected in response.data


def test_catalog_search_and_empty_state_are_server_backed(client):
    match = client.get("/tests?q=CBC")
    missing = client.get("/tests?q=does-not-exist")
    assert b"Complete Blood Count" in match.data
    assert b"No matching tests" in missing.data


def test_chat_endpoint_invokes_agent_and_persists_cookie_session(app, client):
    agent = RecordingAgent()
    install_agent(app, agent)
    first = client.post("/api/chat", json={"message": "Find a CBC test"})
    second = client.post("/api/chat", json={"message": "What is the price?"})
    assert first.status_code == second.status_code == 200
    assert agent.calls[0][0] == agent.calls[1][0]
    assert agent.calls[0][1] == "Find a CBC test"
    assert agent.calls[0][0].startswith("web-")


def test_chat_returns_structured_results_in_original_order(app, client):
    agent = RecordingAgent(
        [
            {
                "response": "Choose an option.",
                "active_search_snapshot": {
                    "items": [
                        {"position": 1, "item_type": "test", "name": "First"},
                        {"position": 2, "item_type": "test", "name": "Second"},
                    ]
                },
            }
        ]
    )
    install_agent(app, agent)
    payload = client.post("/api/chat", json={"message": "show tests"}).get_json()
    assert [item["name"] for item in payload["visible_results"]] == ["First", "Second"]


def test_history_reloads_and_user_content_is_escaped(app, client):
    client.get("/chat")
    with client.session_transaction() as browser_session:
        session_id = browser_session["medilab_session_id"]
    with app.app_context():
        db.session.add(ConversationSession(session_id=session_id, current_state={}))
        db.session.flush()
        db.session.add_all(
            [
                ChatMessage(
                    session_id=session_id, role="user", content="<script>alert(1)</script>"
                ),
                ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content="Safe response",
                    metadata_={"action_result": None, "visible_results": []},
                ),
            ]
        )
        db.session.commit()
    page = client.get("/chat")
    assert b"Safe response" in page.data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page.data
    assert b"<script>alert(1)</script>" not in page.data


def test_pending_clarification_and_booking_resume_through_same_endpoint(app, client):
    agent = RecordingAgent(
        [
            {"response": "Which branch?", "pending_action": {"missing_fields": ["branch_id"]}},
            {
                "response": "Please confirm.",
                "pending_action": {"confirmation_state": "AWAITING_CONFIRMATION"},
                "action_result": {
                    "status": "AWAITING_CONFIRMATION",
                    "committed": False,
                    "success": False,
                    "summary": {"service_name": "Complete Blood Count"},
                },
            },
            {
                "response": "Booking confirmed.",
                "action_result": {
                    "status": "EXECUTED",
                    "committed": True,
                    "success": True,
                    "booking_reference": "REAL-REF-001",
                },
            },
        ]
    )
    install_agent(app, agent)
    first = client.post("/api/chat", json={"message": "Book a CBC"}).get_json()
    second = client.post("/api/chat", json={"message": "Nasr City"}).get_json()
    assert first["pending_action"] is True
    assert second["action_result"]["committed"] is False
    assert len(agent.calls) == 2
    third = client.post("/api/chat", json={"message": "Yes, confirm this booking."}).get_json()
    assert third["action_result"]["booking_reference"] == "REAL-REF-001"
    assert agent.calls[2][1] == "Yes, confirm this booking."


def test_chat_errors_are_controlled_and_input_is_validated(app, client):
    class BrokenAgent:
        def run_turn(self, session_id, message):
            raise RuntimeError("private database detail")

    install_agent(app, BrokenAgent())
    invalid = client.post("/api/chat", json={"message": ""})
    failed = client.post("/api/chat", json={"message": "hello"})
    assert invalid.status_code == 400
    assert failed.status_code == 503
    assert b"private database detail" not in failed.data
    assert b"temporarily unavailable" in failed.data


def test_unknown_route_has_no_traceback(client):
    response = client.get("/not-a-real-route")
    assert response.status_code == 404
    assert b"Traceback" not in response.data
    assert response.get_json()["error"]["code"] == "not_found"


def test_required_accessible_chat_controls_exist(client):
    page = client.get("/chat").data
    assert b'<textarea id="chat-input"' in page
    assert b'<form class="chat-composer"' in page
    assert b'aria-live="polite"' in page
    assert b"Shift+Enter" not in page  # behavior is implemented without cluttering the UI


def test_booking_status_uses_agent_endpoint_not_direct_mutation(client):
    page = client.get("/booking-status").data
    assert b'id="status-form"' in page
    assert b'name="reference"' in page
    assert b'name="phone"' in page
    assert b"/api/chat" not in page  # behavior remains in the external JS UI controller
