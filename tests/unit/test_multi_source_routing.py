"""Tests for validated multi-source read planning and execution."""

from __future__ import annotations

from unittest.mock import patch

from app.agent.nodes.multi_source_node import multi_source_node
from app.agent.nodes.router import route_request
from app.agent.state import create_initial_state


def test_router_history_plus_rag_uses_multi_source() -> None:
    state = create_initial_state("route-history-rag", "What did I book and what is the policy?")
    state["intent"] = "CUSTOMER_HISTORY"
    state["request_plan"] = {
        "requires_customer_history": True,
        "requires_rag": True,
        "requires_structured_data": False,
    }

    assert route_request(state) == "multi_source"


def test_router_history_plus_structured_uses_multi_source() -> None:
    state = create_initial_state("route-history-sql", "What did I book and what does it cost now?")
    state["intent"] = "CUSTOMER_HISTORY"
    state["request_plan"] = {
        "requires_customer_history": True,
        "requires_rag": False,
        "requires_structured_data": True,
    }

    assert route_request(state) == "multi_source"


def test_router_history_only_stays_history_path() -> None:
    state = create_initial_state("route-history-only", "What did I book last time?")
    state["intent"] = "CUSTOMER_HISTORY"
    state["request_plan"] = {"requires_customer_history": True}

    assert route_request(state) == "customer_history"


def test_multi_source_node_preserves_history_and_rag_evidence() -> None:
    state = create_initial_state("multi-source-1", "What did I book and what is the policy?")
    state["request_plan"] = {
        "requires_customer_history": True,
        "requires_rag": True,
        "requires_structured_data": False,
    }
    state["customer_context"] = {"bookings": [{"booking_reference": "MED-1", "items": ["CBC"]}]}

    with (
        patch(
            "app.agent.nodes.multi_source_node.customer_history_node",
            return_value={
                "customer_history_result": state["customer_context"],
                "route_trace": ["customer_history_node"],
                "node_timings": {"customer_history_node": 1.0},
            },
        ),
        patch(
            "app.agent.nodes.multi_source_node.rag_node",
            return_value={
                "rag_result": {
                    "outcome": "GOOD",
                    "chunks": [{"content": "Approved policy evidence"}],
                    "sources": ["Policies.pdf"],
                },
                "route_trace": ["customer_history_node", "rag_node"],
                "node_timings": {"rag_node": 2.0},
            },
        ),
    ):
        update = multi_source_node(state)

    assert update["customer_history_result"]["bookings"][0]["booking_reference"] == "MED-1"
    assert update["rag_result"]["outcome"] == "GOOD"
    assert "customer_history_node" in update["route_trace"]
    assert "rag_node" in update["route_trace"]
