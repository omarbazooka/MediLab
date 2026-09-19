"""Response composition node synthesizing natural answers strictly from verified evidence."""

from __future__ import annotations

import time
from typing import Any

from app.agent.llm.factory import get_llm_provider
from app.agent.state import MediLabAgentState


def _safe_customer_history_for_llm(history: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove contact/internal identifiers while preserving useful verified booking facts."""
    if not history:
        return None
    bookings = []
    for booking in (history.get("bookings") or history.get("recent_bookings") or [])[:5]:
        bookings.append(
            {
                "booking_reference": booking.get("booking_reference"),
                "scheduled_date": booking.get("scheduled_date"),
                "scheduled_time": booking.get("scheduled_time"),
                "status": booking.get("status"),
                "visit_type": booking.get("visit_type"),
                "branch_name": booking.get("branch_name"),
                "items": booking.get("items") or [],
                "total_price": booking.get("total_price"),
                "cancelled_at": booking.get("cancelled_at"),
            }
        )
    return {
        "bookings": bookings,
        "latest_service": history.get("latest_service"),
        "has_active_booking": bool(history.get("has_active_booking")),
        "has_cancellations": bool(history.get("has_cancellations")),
    }


def compose_response(state: MediLabAgentState) -> dict[str, Any]:
    """Compose a coherent natural-language response from trusted evidence."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    if state.get("final_response") and state.get("response_goal") in {
        "CLARIFY",
        "CONTROLLED_ERROR",
    }:
        timings["compose_response"] = (time.perf_counter() - t_start) * 1000
        return {
            "response_draft": state["final_response"],
            "node_timings": timings,
        }

    rag_data = state.get("rag_result") or {}
    user_msg = state.get("normalized_user_message") or state.get("user_message", "")
    language = state.get("language")
    if not language:
        language = "ar" if any("\u0600" <= c <= "\u06ff" for c in user_msg) else "en"

    recent_context = [
        {"role": message.get("role"), "content": message.get("content")}
        for message in (state.get("recent_messages") or [])
        if message.get("role") in {"user", "assistant"} and message.get("content")
    ]

    evidence_bundle = {
        "user_message": user_msg,
        "language": language,
        "intent": state.get("intent"),
        "conversation_context": recent_context,
        "current_selection": {
            "test_id": state.get("selected_test_id"),
            "test_code": state.get("selected_test_code"),
            "test_name": state.get("selected_test_name"),
            "package_id": state.get("selected_package_id"),
            "package_name": state.get("selected_package_name"),
        },
        "customer_history": _safe_customer_history_for_llm(
            state.get("customer_history_result")
        ),
        "structured_facts": state.get("structured_result") or {},
        "rag_outcome": rag_data.get("outcome"),
        "rag_context": rag_data.get("chunks", []),
        "rag_sources": rag_data.get("sources", []),
        "action_result": state.get("action_result"),
        "response_goal": state.get("response_goal", "ANSWER"),
        "clarification_question": state.get("clarification_question"),
    }

    provider = get_llm_provider()
    draft = provider.compose_response(evidence_bundle)

    timings["compose_response"] = (time.perf_counter() - t_start) * 1000

    return {
        "response_draft": draft.text,
        "response_goal": draft.response_goal.value
        if hasattr(draft.response_goal, "value")
        else str(draft.response_goal),
        "node_timings": timings,
    }
