"""LLM understanding and execution planning node."""

from __future__ import annotations

import time
from typing import Any

from app.agent.llm.factory import get_llm_provider
from app.agent.schemas import AgentIntent, RequestPlan
from app.agent.state import MediLabAgentState


def _visible_options_summary(state: MediLabAgentState) -> list[dict[str, Any]]:
    """Expose only the exact currently visible snapshot options to the understanding LLM."""
    snapshot = state.get("active_search_snapshot") or {}
    items = snapshot.get("items") or []
    visible: list[dict[str, Any]] = []
    for position, item in enumerate(items, start=1):
        item_id = item.get("id") or item.get("entity_id")
        item_type = item.get("type") or item.get("entity_type")
        visible.append(
            {
                "position": position,
                "id": item_id,
                "type": item_type,
                "code": item.get("code"),
                "name": item.get("name"),
            }
        )
    return visible


def understand_request(state: MediLabAgentState) -> dict[str, Any]:
    """Parse user natural language into a validated, typed RequestPlan."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    # If safety gate flagged unsafe clinical request, skip understanding.
    if not state.get("is_safe", True):
        timings["understand_request"] = (time.perf_counter() - t_start) * 1000
        return {"node_timings": timings}

    user_msg = state.get("normalized_user_message") or state.get("user_message", "")
    pending = state.get("pending_clarification") or {}

    # Build a compact context summary. The LLM may interpret natural references against
    # visible_options, but deterministic resolution later validates any proposed ID/type
    # against the exact active SearchSnapshot before state can change.
    context_summary = {
        "selected_test_id": state.get("selected_test_id"),
        "selected_package_id": state.get("selected_package_id"),
        "visible_options": _visible_options_summary(state),
        "has_pending_clarification": bool(pending),
        "pending_clarification_target": pending.get("target"),
        "customer_associated": bool(state.get("customer_id")),
    }

    provider = get_llm_provider()
    try:
        plan = provider.understand_request(user_message=user_msg, context_summary=context_summary)
    except Exception:
        # Do not persist arbitrary provider exception text into conversation state.
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
