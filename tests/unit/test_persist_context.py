"""Unit tests for durable agent-context persistence boundaries."""

from __future__ import annotations

from flask import Flask

from app.agent.nodes.persist_context import persist_context
from app.agent.state import create_initial_state
from app.extensions import db
from app.models.conversation import ConversationSession


def test_invalid_session_id_is_not_persisted(app: Flask) -> None:
    """Input-guard errors must not create malformed durable session rows."""
    with app.app_context():
        db.create_all()
        state = create_initial_state("invalid session id!!", "hello")
        state["final_response"] = "Invalid session identifier."
        state["response_goal"] = "CONTROLLED_ERROR"

        persist_context(state)

        assert db.session.query(ConversationSession).count() == 0


def test_pending_action_and_timestamp_state_are_persisted(app: Flask) -> None:
    """Phase-4 boundary state must survive turns without abusing latency as a timestamp."""
    with app.app_context():
        db.create_all()
        state = create_initial_state("persist-valid-1", "I want to book a home visit")
        state["final_response"] = "Booking execution is not active yet."
        state["intent"] = "BOOK_HOME_VISIT"
        state["pending_action"] = {"type": "BOOK_HOME_VISIT", "status": "PENDING"}

        persist_context(state)

        session = (
            db.session.query(ConversationSession).filter_by(session_id="persist-valid-1").one()
        )
        assert session.pending_action == {"type": "BOOK_HOME_VISIT", "status": "PENDING"}
        assert session.current_state.get("last_updated_at")
        assert "last_turn_latency_ms" in session.current_state
        assert "last_updated_turn" not in session.current_state
