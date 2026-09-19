"""Action boundary node serving as the strict boundary for Phase 4 mutations."""

from __future__ import annotations

import time
from typing import Any

from app.agent.state import MediLabAgentState


def action_boundary_node(state: MediLabAgentState) -> dict[str, Any]:
    """Provide clean boundary for action intents without executing mutations or faking success."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("action_boundary_node")

    timings["action_boundary_node"] = (time.perf_counter() - t_start) * 1000

    return {
        "response_goal": "ACTION_NOT_YET_EXECUTABLE",
        "action_result": None,
        "route_trace": routes,
        "node_timings": timings,
    }
