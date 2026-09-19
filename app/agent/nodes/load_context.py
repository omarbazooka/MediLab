"""Context hydration node loading durable session state from PostgreSQL."""

from __future__ import annotations

import time
from typing import Any

from flask import current_app

from app.agent.context import load_conversation_context
from app.agent.state import MediLabAgentState


def load_context(state: MediLabAgentState) -> dict[str, Any]:
    """Hydrate durable conversation state, recent messages, and bounded customer history."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    if not state.get("is_safe", True) and state.get("response_goal") == "CONTROLLED_ERROR":
        timings["load_context"] = (time.perf_counter() - t_start) * 1000
        return {"node_timings": timings}

    session_id = state["session_id"]
    ctx = load_conversation_context(
        session_id=session_id,
        max_messages=int(current_app.config.get("MAX_RECENT_MESSAGES", 10)),
        max_customer_bookings=int(current_app.config.get("MAX_CUSTOMER_BOOKINGS", 5)),
    )

    timings["load_context"] = (time.perf_counter() - t_start) * 1000

    return {
        "customer_id": ctx.get("customer_id"),
        "recent_messages": ctx.get("recent_messages", []),
        "current_state": ctx.get("current_state", {}),
        "selected_test_id": ctx.get("selected_test_id"),
        "selected_test_code": ctx.get("selected_test_code"),
        "selected_test_name": ctx.get("selected_test_name"),
        "selected_package_id": ctx.get("selected_package_id"),
        "selected_package_name": ctx.get("selected_package_name"),
        "active_search_snapshot": ctx.get("active_search_snapshot"),
        "pending_clarification": ctx.get("pending_clarification"),
        "pending_action": ctx.get("pending_action"),
        "customer_context": ctx.get("customer_context"),
        "node_timings": timings,
    }
