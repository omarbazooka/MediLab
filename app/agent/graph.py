"""LangGraph StateGraph builder and MediLab AI agent orchestrator."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.action_boundary_node import action_boundary_node
from app.agent.nodes.clarification_node import clarification_node
from app.agent.nodes.combined_read_node import combined_read_node
from app.agent.nodes.compose_response import compose_response
from app.agent.nodes.customer_history_node import customer_history_node
from app.agent.nodes.general_node import general_node
from app.agent.nodes.input_guard import input_guard
from app.agent.nodes.load_context import load_context
from app.agent.nodes.multi_source_node import multi_source_node
from app.agent.nodes.persist_context import persist_context
from app.agent.nodes.rag_node import rag_node
from app.agent.nodes.resolve_pending_context import resolve_pending_context
from app.agent.nodes.response_validator import response_validator
from app.agent.nodes.router import route_request
from app.agent.nodes.safety_gate import safety_gate
from app.agent.nodes.structured_data_node import structured_data_node
from app.agent.nodes.uncertainty_gate import uncertainty_gate
from app.agent.nodes.understand_request import understand_request
from app.agent.state import MediLabAgentState, create_initial_state

logger = logging.getLogger("medilab.agent.graph")


def _router_node(state: MediLabAgentState) -> dict[str, Any]:
    """Pass-through router node to structure the execution graph cleanly."""
    return {}


def _check_safety_branch(state: MediLabAgentState) -> str:
    """Route clinical/unsafe requests directly to compose_response (safe boundary)."""
    if not state.get("is_safe", True) or state.get("response_goal") == "CONTROLLED_ERROR":
        return "compose_response"
    return "understand_request"


def build_agent_graph() -> Any:
    """Construct and compile the MediLab StateGraph orchestrator."""
    builder = StateGraph(MediLabAgentState)

    builder.add_node("input_guard", input_guard)
    builder.add_node("load_context", load_context)
    builder.add_node("safety_gate", safety_gate)
    builder.add_node("understand_request", understand_request)
    builder.add_node("resolve_pending_context", resolve_pending_context)
    builder.add_node("clarification_node", clarification_node)
    builder.add_node("router_node", _router_node)
    builder.add_node("structured_data_node", structured_data_node)
    builder.add_node("rag_node", rag_node)
    builder.add_node("combined_read_node", combined_read_node)
    builder.add_node("customer_history_node", customer_history_node)
    builder.add_node("multi_source_node", multi_source_node)
    builder.add_node("action_boundary_node", action_boundary_node)
    builder.add_node("general_node", general_node)
    builder.add_node("compose_response", compose_response)
    builder.add_node("response_validator", response_validator)
    builder.add_node("persist_context", persist_context)

    builder.add_edge(START, "input_guard")
    builder.add_edge("input_guard", "load_context")
    builder.add_edge("load_context", "safety_gate")

    builder.add_conditional_edges(
        "safety_gate",
        _check_safety_branch,
        {
            "understand_request": "understand_request",
            "compose_response": "compose_response",
        },
    )

    builder.add_edge("understand_request", "resolve_pending_context")

    builder.add_conditional_edges(
        "resolve_pending_context",
        uncertainty_gate,
        {
            "uncertain": "clarification_node",
            "clear": "router_node",
        },
    )

    builder.add_edge("clarification_node", "persist_context")

    builder.add_conditional_edges(
        "router_node",
        route_request,
        {
            "structured": "structured_data_node",
            "rag": "rag_node",
            "combined_read": "combined_read_node",
            "customer_history": "customer_history_node",
            "multi_source": "multi_source_node",
            "action_boundary": "action_boundary_node",
            "general": "general_node",
            "compose_response": "compose_response",
        },
    )

    builder.add_edge("structured_data_node", "compose_response")
    builder.add_edge("rag_node", "compose_response")
    builder.add_edge("combined_read_node", "compose_response")
    builder.add_edge("customer_history_node", "compose_response")
    builder.add_edge("multi_source_node", "compose_response")
    builder.add_edge("action_boundary_node", "compose_response")
    builder.add_edge("general_node", "compose_response")

    builder.add_edge("compose_response", "response_validator")
    builder.add_edge("response_validator", "persist_context")
    builder.add_edge("persist_context", END)

    return builder.compile()


class MediLabAgent:
    """Production interface wrapping the compiled LangGraph StateGraph orchestrator."""

    def __init__(self) -> None:
        self.graph = build_agent_graph()

    def run_turn(self, session_id: str, message: str) -> dict[str, Any]:
        """Execute a single conversational turn through the StateGraph."""
        initial_state = create_initial_state(session_id=session_id, user_message=message)
        final_state = self.graph.invoke(initial_state)
        return {
            "session_id": final_state.get("session_id"),
            "response": final_state.get("final_response"),
            "intent": final_state.get("intent"),
            "is_safe": final_state.get("is_safe"),
            "safety_classification": final_state.get("safety_classification"),
            "request_plan": final_state.get("request_plan"),
            "entities": final_state.get("entities", {}),
            "structured_result": final_state.get("structured_result"),
            "rag_result": final_state.get("rag_result"),
            "response_goal": final_state.get("response_goal"),
            "route_trace": final_state.get("route_trace", []),
            "pending_clarification": final_state.get("pending_clarification"),
            "pending_action": final_state.get("pending_action"),
            "action_result": final_state.get("action_result"),
            "selected_test_id": final_state.get("selected_test_id"),
            "selected_package_id": final_state.get("selected_package_id"),
            "active_search_snapshot": final_state.get("active_search_snapshot"),
            "total_latency_ms": final_state.get("total_latency_ms", 0.0),
            "node_timings": final_state.get("node_timings", {}),
            "validation": final_state.get("validation_result"),
        }
