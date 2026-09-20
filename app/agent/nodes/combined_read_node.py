"""Combined read node gathering both SQL structured facts and RAG knowledge."""

from __future__ import annotations

import time
from typing import Any

from app.agent.nodes.rag_node import rag_node
from app.agent.nodes.structured_data_node import structured_data_node
from app.agent.state import MediLabAgentState


def combined_read_node(state: MediLabAgentState) -> dict[str, Any]:
    """Execute SQL catalog lookup plus RAG retrieval for multi-source questions."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("combined_read_node")

    working: MediLabAgentState = {**state, "route_trace": routes}
    struct_res = structured_data_node(working)
    routes = list(struct_res.get("route_trace", routes))
    if struct_res.get("response_goal") == "CONTROLLED_ERROR":
        timings["combined_read_node"] = (time.perf_counter() - t_start) * 1000
        return {
            **struct_res,
            "route_trace": routes,
            "node_timings": timings,
        }

    merged_state: MediLabAgentState = {**state, **struct_res, "route_trace": routes}
    rag_res = rag_node(merged_state)
    routes = list(rag_res.get("route_trace", routes))

    timings["combined_read_node"] = (time.perf_counter() - t_start) * 1000

    result: dict[str, Any] = {
        "structured_result": struct_res.get("structured_result"),
        "selected_test_id": struct_res.get("selected_test_id"),
        "selected_package_id": struct_res.get("selected_package_id"),
        "rag_result": rag_res.get("rag_result"),
        "route_trace": routes,
        "node_timings": timings,
    }

    # Preserve a genuine no-knowledge outcome so the composer does not invent RAG facts.
    if rag_res.get("response_goal") == "NO_KNOWLEDGE":
        result["response_goal"] = "NO_KNOWLEDGE"

    # Infrastructure retrieval failure must surface as a controlled error, not be hidden by
    # the successful SQL half of the combined request.
    if rag_res.get("response_goal") == "CONTROLLED_ERROR":
        result.update(
            {
                "response_goal": "CONTROLLED_ERROR",
                "response_draft": rag_res.get("response_draft"),
                "final_response": rag_res.get("final_response"),
                "controlled_errors": rag_res.get("controlled_errors", []),
            }
        )

    return result
