"""Unit tests for clarification_node and bounded clarification loop."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.agent.llm.factory import set_override_llm_provider
from app.agent.llm.fake import FakeLLMProvider
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


def test_clarification_renders_exact_numbered_snapshot_options(app: Flask) -> None:
    """The exact visible sequence is rendered by Python and persisted in SearchSnapshot order."""
    fake_llm = FakeLLMProvider(canned_clarification="Which option do you mean?")
    created_snapshot = SimpleNamespace(
        id=44,
        sequence_no=1,
        query="thyroid",
        status="ACTIVE",
        items=[],
    )

    class FakeConversationRepo:
        def save_snapshot(self, *, session_id, sequence_no, query, criteria, items):
            created_snapshot.sequence_no = sequence_no
            created_snapshot.query = query
            created_snapshot.items = items
            return created_snapshot

    test_option = SimpleNamespace(id=10, name="TSH", price="220.00", code="TSH")
    package_option = SimpleNamespace(id=20, name="Thyroid Wellness Package", price="900.00")

    with app.app_context():
        set_override_llm_provider(fake_llm)
        try:
            state = create_initial_state("session-visible-options", "thyroid")
            state["needs_clarification"] = True
            state["clarification_target"] = "test_selection"
            state["entities"] = {"test_query": "thyroid"}

            with (
                patch(
                    "app.agent.nodes.clarification_node.TestRepository.search",
                    return_value=[test_option],
                ),
                patch(
                    "app.agent.nodes.clarification_node.PackageRepository.search",
                    return_value=[package_option],
                ),
                patch(
                    "app.agent.nodes.clarification_node.ConversationRepository",
                    return_value=FakeConversationRepo(),
                ),
            ):
                update = clarification_node(state)
        finally:
            set_override_llm_provider(None)

    assert "1. TSH (220.00 EGP)" in update["final_response"]
    assert "2. Thyroid Wellness Package (900.00 EGP)" in update["final_response"]
    assert [item["position"] for item in update["active_search_snapshot"]["items"]] == [1, 2]
    assert [item["id"] for item in update["pending_clarification"]["visible_items"]] == [10, 20]


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
        assert "customer service" in update["final_response"].lower()
        assert "19123" not in update["final_response"]


def test_clarification_node_honors_configured_attempt_bound(app: Flask) -> None:
    """MAX_CLARIFICATION_ATTEMPTS must be wired from Flask config, not a dead setting."""
    with app.app_context():
        app.config["MAX_CLARIFICATION_ATTEMPTS"] = 1
        state = create_initial_state("session-clarify-config", "still unsure")
        state["needs_clarification"] = True
        state["clarification_target"] = "test_selection"
        state["pending_clarification"] = {
            "target": "test_selection",
            "attempts": 1,
        }

        update = clarification_node(state)

        assert update["response_goal"] == "ANSWER"
        assert update["pending_clarification"] is None
        assert update["clarification_attempts"] == 2


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
