"""Typed orchestration state for MediLab AI LangGraph agent."""

from __future__ import annotations

from typing import Any, TypedDict


class MediLabAgentState(TypedDict, total=False):
    """Orchestration state passed between LangGraph nodes during a single turn."""

    # Request inputs
    session_id: str
    user_message: str
    normalized_user_message: str

    # Loaded durable context from PostgreSQL
    customer_id: int | None
    recent_messages: list[dict[str, Any]]
    current_state: dict[str, Any]
    customer_context: dict[str, Any] | None
    selected_test_id: int | None
    selected_package_id: int | None
    active_search_snapshot: dict[str, Any] | None
    pending_clarification: dict[str, Any] | None
    pending_action: dict[str, Any] | None

    # Safety gate
    safety_classification: dict[str, Any] | None
    is_safe: bool
    safety_reason: str | None

    # Request understanding
    intent: str | None
    request_plan: dict[str, Any] | None
    entities: dict[str, Any]
    references: list[str]
    ambiguities: list[str]
    language: str

    # Clarification loop
    needs_clarification: bool
    clarification_reason: str | None
    clarification_target: str | None
    clarification_attempts: int
    clarification_question: str | None

    # Execution evidence
    structured_result: dict[str, Any] | None
    rag_result: dict[str, Any] | None
    customer_history_result: dict[str, Any] | None
    action_result: dict[str, Any] | None
    route_trace: list[str]

    # Response & validation
    response_goal: str
    response_draft: str | None
    final_response: str | None
    validation_result: dict[str, Any] | None
    controlled_errors: list[str]

    # Observability & latency measurements
    node_timings: dict[str, float]
    total_latency_ms: float


def create_initial_state(session_id: str, user_message: str) -> MediLabAgentState:
    """Create a clean, isolated agent state for a new graph turn."""
    return {
        "session_id": session_id,
        "user_message": user_message,
        "normalized_user_message": user_message.strip(),
        "customer_id": None,
        "recent_messages": [],
        "current_state": {},
        "customer_context": None,
        "selected_test_id": None,
        "selected_package_id": None,
        "active_search_snapshot": None,
        "pending_clarification": None,
        "pending_action": None,
        "safety_classification": None,
        "is_safe": True,
        "safety_reason": None,
        "intent": None,
        "request_plan": None,
        "entities": {},
        "references": [],
        "language": "ar" if any("\u0600" <= c <= "\u06ff" for c in user_message) else "en",
        "needs_clarification": False,
        "clarification_reason": None,
        "clarification_target": None,
        "clarification_attempts": 0,
        "clarification_question": None,
        "structured_result": None,
        "rag_result": None,
        "customer_history_result": None,
        "action_result": None,
        "route_trace": [],
        "response_goal": "ANSWER",
        "response_draft": None,
        "final_response": None,
        "validation_result": None,
        "controlled_errors": [],
        "node_timings": {},
        "total_latency_ms": 0.0,
    }
