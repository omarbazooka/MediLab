"""General conversation node for greetings, capabilities, and courteous assistance."""

from __future__ import annotations

import time
from typing import Any

from app.agent.state import MediLabAgentState


def general_node(state: MediLabAgentState) -> dict[str, Any]:
    """Route general conversational greetings and questions within MediLab's domain."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("general_node")

    timings["general_node"] = (time.perf_counter() - t_start) * 1000

    return {
        "response_goal": "ANSWER",
        "route_trace": routes,
        "node_timings": timings,
    }
