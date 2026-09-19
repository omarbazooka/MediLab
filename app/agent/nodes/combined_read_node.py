"""Combined read node gathering both SQL structured facts and RAG knowledge."""

from __future__ import annotations

import time
from typing import Any

from app.agent.nodes.rag_node import rag_node
from app.agent.nodes.structured_data_node import structured_data_node
from app.agent.state import MediLabAgentState


def combined_read_node(state: MediLabAgentState) -> dict[str, Any]:
    """Execute both SQL catalog lookup and RAG retrieval for multi-source questions."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("combined_read_node")

    # 1. Execute structured catalog lookup
    struct_res = structured_data_node(state)
    merged_state: MediLabAgentState = {**state, **struct_res}

    # 2. Execute RAG retrieval with resolved test context
    rag_res = rag_node(merged_state)

    timings["combined_read_node"] = (time.perf_counter() - t_start) * 1000

    return {
        "structured_result": struct_res.get("structured_result"),
        "selected_test_id": struct_res.get("selected_test_id"),
        "selected_package_id": struct_res.get("selected_package_id"),
        "rag_result": rag_res.get("rag_result"),
        "route_trace": routes,
        "node_timings": timings,
    }
