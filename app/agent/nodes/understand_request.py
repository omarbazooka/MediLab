"""LLM understanding and execution planning node."""

from __future__ import annotations

import time
from typing import Any

from app.agent.llm.factory import get_llm_provider
from app.agent.schemas import AgentIntent, RequestPlan
from app.agent.state import MediLabAgentState


def understand_request(state: MediLabAgentState) -> dict[str, Any]:
    """Parse user natural language into a validated, typed RequestPlan."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    # If safety gate flagged unsafe clinical request, skip understanding
    if not state.get("is_safe", True):
        timings["understand_request"] = (time.perf_counter() - t_start) * 1000
        return {"node_timings": timings}

    user_msg = state.get("normalized_user_message") or state.get("user_message", "")

    # Build compact context summary for LLM understanding pass
    context_summary = {
        "selected_test_id": state.get("selected_test_id"),
        "selected_package_id": state.get("selected_package_id"),
        "has_active_snapshot": bool(state.get("active_search_snapshot")),
        "has_pending_clarification": bool(state.get("pending_clarification")),
        "pending_clarification_target": (
            state.get("pending_clarification", {}).get("target")
            if state.get("pending_clarification")
            else None
        ),
        "customer_associated": bool(state.get("customer_id")),
    }

    provider = get_llm_provider()
    try:
        plan = provider.understand_request(user_message=user_msg, context_summary=context_summary)
    except Exception as exc:
        # Graceful fallback on unexpected LLM parsing failure
        plan = RequestPlan(primary_intent=AgentIntent.UNKNOWN_AMBIGUOUS, ambiguities=[str(exc)])

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
