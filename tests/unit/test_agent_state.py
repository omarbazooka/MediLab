"""Unit tests for MediLabAgentState construction, defaults, and isolation."""

from __future__ import annotations

from app.agent.state import MediLabAgentState, create_initial_state


def test_create_initial_state_defaults() -> None:
    """Ensure initial agent state has all required keys initialized to safe defaults."""
    state = create_initial_state(session_id="test-session-123", user_message="Hello MediLab")

    assert state["session_id"] == "test-session-123"
    assert state["user_message"] == "Hello MediLab"
    assert state["normalized_user_message"] == "Hello MediLab"
    assert state["is_safe"] is True
    assert state["safety_reason"] is None
    assert state["needs_clarification"] is False
    assert state["clarification_attempts"] == 0
    assert state["route_trace"] == []
    assert state["recent_messages"] == []
    assert state["current_state"] == {}
    assert state["customer_context"] is None
    assert state["structured_result"] is None
    assert state["rag_result"] is None
    assert state["action_result"] is None
    assert state["final_response"] is None
    assert state["total_latency_ms"] == 0.0


def test_agent_state_isolation() -> None:
    """Ensure multiple state instances do not share mutable references."""
    state_a = create_initial_state(session_id="session-a", user_message="Message A")
    state_b = create_initial_state(session_id="session-b", user_message="Message B")

    state_a["route_trace"].append("node_1")
    state_a["controlled_errors"].append("error_1")
    state_a["entities"]["test"] = "CBC"

    assert state_b["route_trace"] == []
    assert state_b["controlled_errors"] == []
    assert "test" not in state_b["entities"]


def test_typeddict_conformance() -> None:
    """Verify that MediLabAgentState can be populated with valid orchestration fields."""
    custom_state: MediLabAgentState = {
        "session_id": "sess-456",
        "user_message": "How much is TSH?",
        "normalized_user_message": "How much is TSH?",
        "intent": "TEST_PRICE",
        "is_safe": True,
        "selected_test_id": 1,
        "route_trace": ["input_guard", "load_context", "structured_data_node"],
    }
    assert custom_state["intent"] == "TEST_PRICE"
    assert custom_state["selected_test_id"] == 1
