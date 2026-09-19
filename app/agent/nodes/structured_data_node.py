"""Structured data node querying PostgreSQL catalog, branches, and availability."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.state import MediLabAgentState
from app.services.branch_service import BranchService
from app.services.package_service import PackageService
from app.services.test_service import TestService

logger = logging.getLogger("medilab.agent.structured")


def _controlled_structured_error(language: str) -> str:
    return (
        "عذراً، تعذر الوصول إلى بيانات ميدي لاب الحالية. يرجى إعادة المحاولة بعد قليل."
        if language == "ar"
        else "I’m sorry, MediLab’s current service data is temporarily unavailable. Please try again shortly."
    )


def structured_data_node(state: MediLabAgentState) -> dict[str, Any]:
    """Fetch authoritative structured facts from PostgreSQL using domain services."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("structured_data_node")

    test_service = TestService()
    package_service = PackageService()
    branch_service = BranchService()

    structured_facts: dict[str, Any] = {}
    selected_test_id = state.get("selected_test_id")
    selected_package_id = state.get("selected_package_id")
    entities = state.get("entities", {})

    try:
        # 1. Resolve test details.
        test_obj = None
        if selected_test_id:
            test_obj = test_service.get_test_details(selected_test_id)
        elif entities.get("test_query"):
            query = str(entities["test_query"]).strip()
            test_obj = test_service.get_test_by_code(query)
            if not test_obj:
                matched_tests = test_service.search_tests(query=query, active_only=True)
                # The uncertainty gate should prevent ambiguous multi-match requests from
                # reaching this point. A single match is safe to resolve deterministically.
                if len(matched_tests) == 1:
                    test_obj = matched_tests[0]

        if test_obj:
            selected_test_id = test_obj.id
            structured_facts["test"] = {
                "id": test_obj.id,
                "code": test_obj.code,
                "name": test_obj.name,
                "description": test_obj.short_description,
                "price": f"{test_obj.price:.2f} EGP",
                "sample_type": test_obj.sample_type,
                "turnaround": test_obj.result_turnaround_text,
            }

        # 2. Resolve package details.
        package_obj = None
        if selected_package_id:
            package_obj = package_service.get_package_details(selected_package_id)
        elif entities.get("package_query"):
            query = str(entities["package_query"]).strip()
            search_query = None if query.lower() in ("all", "*", "") else query
            matched_packages = package_service.search_packages(query=search_query, active_only=True)
            if matched_packages:
                structured_facts["packages"] = [
                    {
                        "id": package.id,
                        "name": package.name,
                        "description": package.description,
                        "price": f"{package.price:.2f} EGP",
                    }
                    for package in matched_packages
                ]
                if len(matched_packages) == 1:
                    package_obj = matched_packages[0]

        if package_obj:
            selected_package_id = package_obj.id
            structured_facts["package"] = {
                "id": package_obj.id,
                "name": package_obj.name,
                "description": package_obj.description,
                "price": f"{package_obj.price:.2f} EGP",
                "tests": [test.name for test in (package_obj.tests or [])],
            }

        # 3. Resolve branch information.
        if entities.get("branch_query") or state.get("intent") == "BRANCH_INFO":
            branches = branch_service.list_active_branches()
            structured_facts["branches"] = [
                {
                    "id": branch.id,
                    "name": branch.name,
                    "address": branch.address,
                    "phone": branch.phone,
                    "opening_hours": branch.opening_hours_json,
                }
                for branch in branches
            ]
    except Exception:
        logger.error("Structured-data lookup failed; returning controlled unavailable state.")
        timings["structured_data_node"] = (time.perf_counter() - t_start) * 1000
        language = state.get("language", "en")
        fallback = _controlled_structured_error(language)
        return {
            "structured_result": {},
            "route_trace": routes,
            "response_goal": "CONTROLLED_ERROR",
            "response_draft": fallback,
            "final_response": fallback,
            "controlled_errors": list(state.get("controlled_errors", []))
            + ["Structured data unavailable."],
            "node_timings": timings,
        }

    timings["structured_data_node"] = (time.perf_counter() - t_start) * 1000

    return {
        "structured_result": structured_facts,
        "selected_test_id": selected_test_id,
        "selected_package_id": selected_package_id,
        "route_trace": routes,
        "node_timings": timings,
    }
