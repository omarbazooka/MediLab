"""Uncertainty gate conditional edge for LangGraph."""

from __future__ import annotations

from app.agent.state import MediLabAgentState


def uncertainty_gate(state: MediLabAgentState) -> str:
    """Determine whether to route to clarification node or continue to execution router."""
    # If clinical safety was flagged, route forward to compose_response (safe boundary)
    if not state.get("is_safe", True):
        return "clear"

    # If input guard flagged an error, route forward to persist and exit
    if state.get("response_goal") == "CONTROLLED_ERROR":
        return "clear"

    # If clarification is requested or pending without resolution
    if state.get("needs_clarification", False) or state.get("pending_clarification"):
        return "uncertain"

    # If ambiguities exist and neither test nor package is selected
    if (
        state.get("ambiguities")
        and not state.get("selected_test_id")
        and not state.get("selected_package_id")
    ):
        return "uncertain"

    return "clear"
