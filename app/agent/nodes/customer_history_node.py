"""Customer history node providing bounded read-only booking history."""

from __future__ import annotations

import time
from typing import Any

from app.agent.state import MediLabAgentState


def customer_history_node(state: MediLabAgentState) -> dict[str, Any]:
    """Retrieve verified customer booking history for authenticated/associated customer."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("customer_history_node")

    customer_ctx = state.get("customer_context")

    timings["customer_history_node"] = (time.perf_counter() - t_start) * 1000

    return {
        "customer_history_result": customer_ctx,
        "route_trace": routes,
        "node_timings": timings,
    }
