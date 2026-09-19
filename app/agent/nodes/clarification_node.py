"""Clarification node generating contextual questions and bounding attempts."""

from __future__ import annotations

import time
from typing import Any

from app.agent.llm.factory import get_llm_provider
from app.agent.state import MediLabAgentState
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.package_repository import PackageRepository
from app.repositories.test_repository import TestRepository

MAX_CLARIFICATION_ATTEMPTS = 2


def clarification_node(state: MediLabAgentState) -> dict[str, Any]:
    """Generate a single focused clarification question and persist pending clarification state."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    session_id = state["session_id"]
    current_attempts = 0
    if state.get("pending_clarification"):
        current_attempts = state["pending_clarification"].get("attempts", 0)
    attempts = current_attempts + 1

    language = state.get("language", "en")
    target = state.get("clarification_target") or "service_selection"
    reason = state.get("clarification_reason") or "Multiple options or ambiguous entity."

    # If attempts exceed the bound, provide a polite fallback and human support referral
    if attempts > MAX_CLARIFICATION_ATTEMPTS:
        timings["clarification_node"] = (time.perf_counter() - t_start) * 1000
        fallback_text = (
            "لم نتمكن من تحديد الخدمة بدقة. يمكنك التحدث مباشرة مع خدمة عملاء ميدي لاب عبر الخط الساخن 19123 أو زيارة أقرب فرع."
            if language == "ar"
            else "We could not determine your specific request after multiple attempts. Please contact MediLab customer service at 19123 or visit your nearest branch for personal assistance."
        )
        return {
            "needs_clarification": False,
            "pending_clarification": None,
            "clarification_attempts": attempts,
            "response_goal": "ANSWER",
            "response_draft": fallback_text,
            "final_response": fallback_text,
            "node_timings": timings,
        }

    # Discover candidate options from real catalog if inquiry is about a category (e.g. thyroid)
    options: list[str] = []
    snapshot_items: list[dict[str, Any]] = []

    entities = state.get("entities", {})
    query = entities.get("test_query") or state.get("normalized_user_message", "")

    test_repo = TestRepository()
    pkg_repo = PackageRepository()

    matched_tests = test_repo.search(query=query, active_only=True)
    matched_packages = pkg_repo.search(query=query, active_only=True)

    # If searching "thyroid", also check packages with thyroid description
    if "thyroid" in query.lower() or "غدة" in query:
        vitality_pkg = pkg_repo.get_by_name("Vitality & Wellness Panel")
        if vitality_pkg and vitality_pkg not in matched_packages:
            matched_packages.append(vitality_pkg)

    for t in matched_tests:
        options.append(f"{t.name} ({t.price} EGP)")
        snapshot_items.append(
            {
                "type": "test",
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "price": str(t.price),
            }
        )
    for p in matched_packages:
        options.append(f"{p.name} ({p.price} EGP)")
        snapshot_items.append(
            {
                "type": "package",
                "id": p.id,
                "name": p.name,
                "price": str(p.price),
            }
        )

    # Save SearchSnapshot if candidates were found and no active snapshot exists
    active_snapshot = state.get("active_search_snapshot")
    if snapshot_items:
        conv_repo = ConversationRepository()
        seq = 1
        if active_snapshot:
            seq = active_snapshot.get("sequence_no", 0) + 1
        created_snap = conv_repo.save_snapshot(
            session_id=session_id,
            sequence_no=seq,
            query=query,
            criteria={"target": target},
            items=snapshot_items,
        )
        active_snapshot = {
            "id": created_snap.id,
            "sequence_no": created_snap.sequence_no,
            "query": created_snap.query,
            "items": created_snap.items,
        }

    provider = get_llm_provider()
    question = provider.generate_clarification(
        target=target,
        reason=reason,
        options=options,
        language=language,
    )

    pending_clarification_data = {
        "target": target,
        "attempts": attempts,
        "options": options,
        "question": question,
    }

    timings["clarification_node"] = (time.perf_counter() - t_start) * 1000

    routes = list(state.get("route_trace", []))
    routes.append("clarification_node")

    return {
        "pending_clarification": pending_clarification_data,
        "active_search_snapshot": active_snapshot,
        "clarification_attempts": attempts,
        "clarification_question": question,
        "response_goal": "CLARIFY",
        "response_draft": question,
        "final_response": question,
        "route_trace": routes,
        "node_timings": timings,
    }
