"""Router conditional edge directing execution based on the validated RequestPlan."""

from __future__ import annotations

from app.agent.schemas import AgentIntent
from app.agent.state import MediLabAgentState


def route_request(state: MediLabAgentState) -> str:
    """Determine the execution branch from the validated RequestPlan."""
    if not state.get("is_safe", True):
        return "compose_response"

    if state.get("response_goal") == "CONTROLLED_ERROR":
        return "compose_response"

    plan = state.get("request_plan") or {}
    intent = state.get("intent") or ""

    if plan.get("action_intent") or intent in {
        AgentIntent.BOOK_BRANCH_VISIT.value,
        AgentIntent.BOOK_HOME_VISIT.value,
        AgentIntent.CHECK_BOOKING.value,
        AgentIntent.CANCEL_BOOKING.value,
    }:
        return "action_boundary"

    requires_history = bool(
        plan.get("requires_customer_history") or intent == AgentIntent.CUSTOMER_HISTORY.value
    )
    requires_structured = bool(plan.get("requires_structured_data", False))
    requires_rag = bool(plan.get("requires_rag", False))

    # Customer-history questions may also need current catalog facts and/or approved
    # policy knowledge. Do not let the history flag eclipse the other requested sources.
    if requires_history and (requires_structured or requires_rag):
        return "multi_source"

    if requires_history:
        return "customer_history"

    if requires_structured and requires_rag:
        return "combined_read"

    if requires_rag or intent in {
        AgentIntent.PREPARATION.value,
        AgentIntent.POLICY.value,
        AgentIntent.FAQ.value,
        AgentIntent.HOME_SERVICE_INFO.value,
        AgentIntent.CANCELLATION_POLICY.value,
    }:
        return "rag"

    if requires_structured or intent in {
        AgentIntent.TEST_SEARCH.value,
        AgentIntent.TEST_DETAILS.value,
        AgentIntent.TEST_DEFINITION.value,
        AgentIntent.TEST_PRICE.value,
        AgentIntent.SAMPLE_TYPE.value,
        AgentIntent.RESULT_TURNAROUND.value,
        AgentIntent.PACKAGE_SEARCH.value,
        AgentIntent.PACKAGE_DETAILS.value,
        AgentIntent.PACKAGE_PRICE.value,
        AgentIntent.BRANCH_INFO.value,
        AgentIntent.AVAILABILITY.value,
    }:
        return "structured"

    return "general"
