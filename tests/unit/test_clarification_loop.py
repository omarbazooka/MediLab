"""Unit tests for clarification_node and bounded clarification loop."""

from __future__ import annotations

from flask import Flask

from app.agent.nodes.clarification_node import MAX_CLARIFICATION_ATTEMPTS, clarification_node
from app.agent.nodes.resolve_pending_context import resolve_pending_context
from app.agent.state import create_initial_state
from app.extensions import db


def test_clarification_node_first_attempt(app: Flask) -> None:
    """First clarification attempt produces targeted question and sets pending state."""
    with app.app_context():
        db.create_all()
        state = create_initial_state("session-clarify-1", "I want a thyroid test")
        state["needs_clarification"] = True
        state["clarification_target"] = "test_selection"

        update = clarification_node(state)

        assert update["response_goal"] == "CLARIFY"
        assert update["clarification_attempts"] == 1
        assert update["pending_clarification"] is not None
        assert update["pending_clarification"]["target"] == "test_selection"
        assert update["pending_clarification"]["attempts"] == 1
        assert "clarification_node" in update["node_timings"]


def test_clarification_node_bounded_fallback(app: Flask) -> None:
    """Exceeding MAX_CLARIFICATION_ATTEMPTS triggers safe human support fallback."""
    with app.app_context():
        state = create_initial_state("session-clarify-2", "still unsure")
        state["needs_clarification"] = True
        state["clarification_target"] = "test_selection"
        state["pending_clarification"] = {
            "target": "test_selection",
            "attempts": MAX_CLARIFICATION_ATTEMPTS,
        }

        update = clarification_node(state)

        assert update["response_goal"] == "ANSWER"
        assert update["needs_clarification"] is False
        assert update["pending_clarification"] is None
        assert (
            "19123" in update["final_response"]
            or "customer service" in update["final_response"].lower()
        )


def test_resolve_pending_context_clears_on_resolution(app: Flask) -> None:
    """When the user provides a valid resolving response, pending_clarification is cleared."""
    with app.app_context():
        db.create_all()
        state = create_initial_state("session-clarify-3", "TSH")
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}
        state["entities"] = {"test_query": "TSH"}

        update = resolve_pending_context(state)

        assert update["pending_clarification"] is None
        assert update["needs_clarification"] is False
