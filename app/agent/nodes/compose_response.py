"""Response composition node synthesizing natural answers strictly from verified evidence."""

from __future__ import annotations

import time
from typing import Any

from app.agent.llm.factory import get_llm_provider
from app.agent.state import MediLabAgentState


def compose_response(state: MediLabAgentState) -> dict[str, Any]:
    """Compose a coherent natural-language response synthesized strictly from trusted evidence."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    # If already set by clarification or controlled error, preserve it
    if state.get("final_response") and state.get("response_goal") in {
        "CLARIFY",
        "CONTROLLED_ERROR",
    }:
        timings["compose_response"] = (time.perf_counter() - t_start) * 1000
        return {
            "response_draft": state["final_response"],
            "node_timings": timings,
        }

    # Prepare evidence bundle
    rag_data = state.get("rag_result") or {}
    user_msg = state.get("normalized_user_message") or state.get("user_message", "")
    lang = state.get("language")
    if not lang:
        lang = "ar" if any("\u0600" <= c <= "\u06ff" for c in user_msg) else "en"

    evidence_bundle = {
        "user_message": user_msg,
        "language": lang,
        "intent": state.get("intent"),
        "conversation_context": [
            {"role": m["role"], "content": m["content"]}
            for m in state.get("recent_messages", [])[-4:]
        ],
        "customer_history": state.get("customer_history_result"),
        "structured_facts": state.get("structured_result") or {},
        "rag_context": rag_data.get("chunks", []),
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
