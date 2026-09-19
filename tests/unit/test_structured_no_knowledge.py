"""Tests for structured-data no-answer, availability, and controlled-error semantics."""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
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


def test_availability_uses_verified_slot_service(app: Flask) -> None:
    branch = SimpleNamespace(id=3, name="Maadi")
    slot = SimpleNamespace(
        id=91,
        branch_id=3,
        branch=branch,
        visit_type="BRANCH",
        date=date(2026, 9, 20),
        time=time(9, 30),
        capacity=4,
        reserved_count=1,
    )

    with app.app_context():
        state = create_initial_state("structured-availability", "Any slots on 2026-09-20?")
        state["intent"] = "AVAILABILITY"
        state["entities"] = {
            "branch_id": 3,
            "visit_type": "BRANCH",
            "target_date": "2026-09-20",
        }

        with patch(
            "app.agent.nodes.structured_data_node.BranchService.find_available_slots",
            return_value=[slot],
        ) as find_slots:
            update = structured_data_node(state)

    find_slots.assert_called_once_with(
        branch_id=3,
        visit_type="BRANCH",
        target_date=date(2026, 9, 20),
        active_only=True,
    )
    assert update["structured_result"]["availability_slots"][0] == {
        "id": 91,
        "branch_id": 3,
        "branch_name": "Maadi",
        "visit_type": "BRANCH",
        "date": "2026-09-20",
        "time": "09:30",
        "remaining_capacity": 3,
    }


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
