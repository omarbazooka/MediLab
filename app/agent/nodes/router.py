"""Router conditional edge directing execution based on the validated RequestPlan."""

from __future__ import annotations

from app.agent.schemas import AgentIntent
from app.agent.state import MediLabAgentState


def route_request(state: MediLabAgentState) -> str:
    """Determine the specific execution branch based on the validated RequestPlan."""
    # If safety gate flagged unsafe clinical request, route straight to compose_response
    if not state.get("is_safe", True):
        return "compose_response"

    # If input guard flagged error, route straight to persist
    if state.get("response_goal") == "CONTROLLED_ERROR":
        return "compose_response"

    plan = state.get("request_plan") or {}
    intent = state.get("intent") or ""

    if plan.get("requires_customer_history") or intent == AgentIntent.CUSTOMER_HISTORY.value:
        return "customer_history"

    if plan.get("action_intent") or intent in {
        AgentIntent.BOOK_BRANCH_VISIT.value,
        AgentIntent.BOOK_HOME_VISIT.value,
        AgentIntent.CHECK_BOOKING.value,
        AgentIntent.CANCEL_BOOKING.value,
    }:
        return "action_boundary"

    req_struct = plan.get("requires_structured_data", False)
    req_rag = plan.get("requires_rag", False)

    if req_struct and req_rag:
        return "combined_read"

    if req_rag or intent in {
        AgentIntent.PREPARATION.value,
        AgentIntent.POLICY.value,
        AgentIntent.FAQ.value,
        AgentIntent.HOME_SERVICE_INFO.value,
        AgentIntent.CANCELLATION_POLICY.value,
    }:
        return "rag"

    if req_struct or intent in {
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
