"""Multi-source read node combining customer history with SQL and/or RAG evidence."""

from __future__ import annotations

import time
from typing import Any

from app.agent.nodes.customer_history_node import customer_history_node
from app.agent.nodes.rag_node import rag_node
from app.agent.nodes.structured_data_node import structured_data_node
from app.agent.state import MediLabAgentState


def multi_source_node(state: MediLabAgentState) -> dict[str, Any]:
    """Gather every trusted read source requested by the validated RequestPlan.

    This path exists for questions that legitimately require customer history plus
    another source, for example a historical booking fact together with a policy
    from RAG or a current catalog fact from SQL. It never performs mutations.
    """
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("multi_source_node")

    plan = state.get("request_plan") or {}
    working: MediLabAgentState = {**state, "route_trace": routes}
    result: dict[str, Any] = {}

    # Customer history is already hydrated and ownership-checked in load_context.
    history_res = customer_history_node(working)
    working = {**working, **history_res}
    result["customer_history_result"] = history_res.get("customer_history_result")
    routes = list(history_res.get("route_trace", routes))

    if plan.get("requires_structured_data"):
        struct_res = structured_data_node({**working, "route_trace": routes})
        working = {**working, **struct_res}
        routes = list(struct_res.get("route_trace", routes))
        result.update(
            {
                "structured_result": struct_res.get("structured_result"),
                "selected_test_id": struct_res.get("selected_test_id"),
                "selected_package_id": struct_res.get("selected_package_id"),
            }
        )
        if struct_res.get("response_goal") == "CONTROLLED_ERROR":
            timings.update(struct_res.get("node_timings", {}))
            timings["multi_source_node"] = (time.perf_counter() - t_start) * 1000
            return {
                **result,
                "response_goal": "CONTROLLED_ERROR",
                "response_draft": struct_res.get("response_draft"),
                "final_response": struct_res.get("final_response"),
                "controlled_errors": struct_res.get("controlled_errors", []),
                "route_trace": routes,
                "node_timings": timings,
            }

    if plan.get("requires_rag"):
        rag_res = rag_node({**working, **result, "route_trace": routes})
        routes = list(rag_res.get("route_trace", routes))
        result["rag_result"] = rag_res.get("rag_result")
        if rag_res.get("response_goal") == "CONTROLLED_ERROR":
            timings.update(rag_res.get("node_timings", {}))
            timings["multi_source_node"] = (time.perf_counter() - t_start) * 1000
            return {
                **result,
                "response_goal": "CONTROLLED_ERROR",
                "response_draft": rag_res.get("response_draft"),
                "final_response": rag_res.get("final_response"),
                "controlled_errors": rag_res.get("controlled_errors", []),
                "route_trace": routes,
                "node_timings": timings,
            }

    # If one requested source legitimately has no knowledge, keep the other verified
    # evidence available and let the composer explain the missing portion honestly.
    timings.update(working.get("node_timings", {}))
    timings["multi_source_node"] = (time.perf_counter() - t_start) * 1000
    result.update({"route_trace": routes, "node_timings": timings})
    return result
