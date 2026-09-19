"""LLM understanding and execution planning node."""

from __future__ import annotations

import time
from typing import Any

from app.agent.llm.factory import get_llm_provider
from app.agent.schemas import AgentIntent, RequestPlan
from app.agent.state import MediLabAgentState


def _visible_options_summary(state: MediLabAgentState) -> list[dict[str, Any]]:
    """Expose only the exact currently visible ACTIVE snapshot options to the understanding LLM."""
    snapshot = state.get("active_search_snapshot") or {}
    if str(snapshot.get("status", "ACTIVE")).upper() != "ACTIVE":
        return []
    items = snapshot.get("items") or []
    visible: list[dict[str, Any]] = []
    for position, item in enumerate(items, start=1):
        visible.append(
            {
                "position": position,
                "id": item.get("id") or item.get("entity_id"),
                "type": item.get("type") or item.get("entity_type"),
                "code": item.get("code"),
                "name": item.get("name"),
            }
        )
    return visible


def _recent_conversation_summary(state: MediLabAgentState) -> list[dict[str, Any]]:
    """Return only bounded role/content history already loaded for this session."""
    messages = state.get("recent_messages") or []
    return [
        {"role": message.get("role"), "content": message.get("content")}
        for message in messages
        if message.get("role") in {"user", "assistant"} and message.get("content")
    ]


def _customer_history_summary(state: MediLabAgentState) -> dict[str, Any] | None:
    """Expose relevant read-only history facts without phone numbers or internal customer IDs."""
    context = state.get("customer_context") or {}
    if not context:
        return None

    recent_bookings = []
    for booking in (context.get("recent_bookings") or [])[:3]:
        recent_bookings.append(
            {
                "booking_reference": booking.get("booking_reference"),
                "scheduled_date": booking.get("scheduled_date"),
                "scheduled_time": booking.get("scheduled_time"),
                "status": booking.get("status"),
                "visit_type": booking.get("visit_type"),
                "branch_name": booking.get("branch_name"),
                "items": booking.get("items") or [],
                "total_price": booking.get("total_price"),
            }
        )

    return {
        "recent_bookings": recent_bookings,
        "latest_service": context.get("latest_service"),
        "has_active_booking": bool(context.get("has_active_booking")),
        "has_cancellations": bool(context.get("has_cancellations")),
    }


def understand_request(state: MediLabAgentState) -> dict[str, Any]:
    """Parse natural language into a validated typed RequestPlan using bounded durable context."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    if not state.get("is_safe", True):
        timings["understand_request"] = (time.perf_counter() - t_start) * 1000
        return {"node_timings": timings}

    user_msg = state.get("normalized_user_message") or state.get("user_message", "")
    pending = state.get("pending_clarification") or {}
    visible_options = _visible_options_summary(state)

    context_summary = {
        "recent_conversation": _recent_conversation_summary(state),
        "selected_test": (
            {
                "id": state.get("selected_test_id"),
                "code": state.get("selected_test_code"),
                "name": state.get("selected_test_name"),
            }
            if state.get("selected_test_id")
            else None
        ),
        "selected_package": (
            {
                "id": state.get("selected_package_id"),
                "name": state.get("selected_package_name"),
            }
            if state.get("selected_package_id")
            else None
        ),
        "has_active_snapshot": bool(visible_options),
        "visible_options": visible_options,
        "has_pending_clarification": bool(pending),
        "pending_clarification_target": pending.get("target"),
        "customer_associated": bool(state.get("customer_id")),
        "customer_history_summary": _customer_history_summary(state),
    }

    provider = get_llm_provider()
    try:
        plan = provider.understand_request(user_message=user_msg, context_summary=context_summary)
    except Exception:
        plan = RequestPlan(
            primary_intent=AgentIntent.UNKNOWN_AMBIGUOUS,
            ambiguities=["Request understanding unavailable."],
            needs_clarification=True,
            clarification_target=pending.get("target") or "request_meaning",
        )

    timings["understand_request"] = (time.perf_counter() - t_start) * 1000

    intent_val = (
        plan.primary_intent.value
        if hasattr(plan.primary_intent, "value")
        else str(plan.primary_intent)
    )

    return {
        "intent": intent_val,
        "request_plan": plan.model_dump(),
        "entities": plan.entities,
        "references": plan.references,
        "ambiguities": plan.ambiguities,
        "language": plan.language,
        "needs_clarification": plan.needs_clarification,
        "clarification_target": plan.clarification_target,
        "node_timings": timings,
    }
