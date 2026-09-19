"""Tests for structured-data no-answer and controlled-error semantics."""

from __future__ import annotations

from unittest.mock import patch

from flask import Flask

from app.agent.nodes.structured_data_node import structured_data_node
from app.agent.state import create_initial_state


def test_missing_test_returns_no_knowledge(app: Flask) -> None:
    with app.app_context():
        state = create_initial_state("structured-missing", "How much is XYZ?")
        state["intent"] = "TEST_PRICE"
        state["entities"] = {"test_query": "XYZ"}

        with (
            patch("app.agent.nodes.structured_data_node.TestService.get_test_by_code", return_value=None),
            patch("app.agent.nodes.structured_data_node.TestService.search_tests", return_value=[]),
        ):
            update = structured_data_node(state)

    assert update["response_goal"] == "NO_KNOWLEDGE"
    assert update["structured_result"] == {}


def test_structured_service_exception_returns_controlled_error(app: Flask) -> None:
    with app.app_context():
        state = create_initial_state("structured-error", "How much is CBC?")
        state["intent"] = "TEST_PRICE"
        state["entities"] = {"test_query": "CBC"}

        with patch(
            "app.agent.nodes.structured_data_node.TestService.get_test_by_code",
            side_effect=RuntimeError("database unavailable"),
        ):
            update = structured_data_node(state)

    assert update["response_goal"] == "CONTROLLED_ERROR"
    assert "database unavailable" not in update["final_response"]
    assert "Structured data unavailable." in update["controlled_errors"]
