"""Uncertainty gate conditional edge for LangGraph."""

from __future__ import annotations

from app.agent.schemas import AgentIntent
from app.agent.state import MediLabAgentState
from app.repositories.package_repository import PackageRepository
from app.repositories.test_repository import TestRepository


def uncertainty_gate(state: MediLabAgentState) -> str:
    """Determine whether to clarify or continue using evidence beyond LLM self-report."""
    if not state.get("is_safe", True):
        return "clear"

    if state.get("response_goal") == "CONTROLLED_ERROR":
        return "clear"

    if state.get("needs_clarification", False) or state.get("pending_clarification"):
        return "uncertain"

    intent = state.get("intent") or ""
    if intent in {
        AgentIntent.UNKNOWN_AMBIGUOUS.value,
        AgentIntent.GENERAL_CONVERSATION.value,
    } and not state.get("needs_clarification", False):
        return "clear"

    if (
        state.get("ambiguities")
        and not state.get("selected_test_id")
        and not state.get("selected_package_id")
    ):
        return "uncertain"

    # Deterministic evidence signal: if the LLM extracted a catalog query but more than
    # one real visible candidate plausibly matches, do not let a downstream node pick
    # the first row. Ask the user instead. This does not replace LLM understanding; it
    # validates whether the understood entity is uniquely actionable.
    if not state.get("selected_test_id") and not state.get("selected_package_id"):
        entities = state.get("entities", {})
        test_query = entities.get("test_query")
        if isinstance(test_query, str) and test_query.strip():
            tests = TestRepository().search(query=test_query.strip(), active_only=True)
            packages = PackageRepository().search(query=test_query.strip(), active_only=True)
            if len(tests) + len(packages) > 1:
                return "uncertain"

    return "clear"
