"""Structured data node querying PostgreSQL catalog, branches, and availability."""

from __future__ import annotations

import time
from typing import Any

from app.agent.state import MediLabAgentState
from app.services.branch_service import BranchService
from app.services.package_service import PackageService
from app.services.test_service import TestService


def structured_data_node(state: MediLabAgentState) -> dict[str, Any]:
    """Fetch authoritative structured facts from PostgreSQL using domain services."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("structured_data_node")

    test_service = TestService()
    pkg_service = PackageService()
    branch_service = BranchService()

    structured_facts: dict[str, Any] = {}
    selected_test_id = state.get("selected_test_id")
    selected_package_id = state.get("selected_package_id")
    entities = state.get("entities", {})

    # 1. Resolve Test Details
    test_obj = None
    if selected_test_id:
        test_obj = test_service.get_test_details(selected_test_id)
    elif entities.get("test_query"):
        q = str(entities["test_query"]).strip()
        test_obj = test_service.get_test_by_code(q)
        if not test_obj:
            matched = test_service.search_tests(query=q, active_only=True)
            if matched:
                test_obj = matched[0]

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

    # 2. Resolve Package Details
    pkg_obj = None
    if selected_package_id:
        pkg_obj = pkg_service.get_package_details(selected_package_id)
    elif entities.get("package_query"):
        q = str(entities["package_query"]).strip()
        search_q = None if q.lower() in ("all", "*", "") else q
        matched_pkgs = pkg_service.search_packages(query=search_q, active_only=True)
        if matched_pkgs:
            structured_facts["packages"] = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "price": f"{p.price:.2f} EGP",
                }
                for p in matched_pkgs
            ]
            if len(matched_pkgs) == 1 or q.lower() not in ("all", "*", ""):
                pkg_obj = matched_pkgs[0]

    if pkg_obj:
        selected_package_id = pkg_obj.id
        structured_facts["package"] = {
            "id": pkg_obj.id,
            "name": pkg_obj.name,
            "description": pkg_obj.description,
            "price": f"{pkg_obj.price:.2f} EGP",
            "tests": [t.name for t in (pkg_obj.tests or [])],
        }

    # 3. Resolve Branch Info
    if entities.get("branch_query") or state.get("intent") == "BRANCH_INFO":
        branches = branch_service.list_active_branches()
        structured_facts["branches"] = [
            {
                "id": b.id,
                "name": b.name,
                "address": b.address,
                "phone": b.phone,
                "opening_hours": b.opening_hours_json,
            }
            for b in branches
        ]

    timings["structured_data_node"] = (time.perf_counter() - t_start) * 1000

    return {
        "structured_result": structured_facts,
        "selected_test_id": selected_test_id,
        "selected_package_id": selected_package_id,
        "route_trace": routes,
        "node_timings": timings,
    }
