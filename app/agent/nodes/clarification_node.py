"""Clarification node generating contextual questions and bounding attempts."""

from __future__ import annotations

import time
from typing import Any

from flask import current_app

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
    max_attempts = int(
        current_app.config.get("MAX_CLARIFICATION_ATTEMPTS", MAX_CLARIFICATION_ATTEMPTS)
    )

    language = state.get("language", "en")
    target = state.get("clarification_target") or "service_selection"
    reason = state.get("clarification_reason") or "Multiple options or ambiguous entity."

    # If attempts exceed the bound, provide a polite fallback and human-support referral.
    # Do not invent a phone number that is not backed by verified business data.
    if attempts > max_attempts:
        timings["clarification_node"] = (time.perf_counter() - t_start) * 1000
        fallback_text = (
            "لم نتمكن من تحديد الخدمة بدقة بعد عدة محاولات. يرجى التواصل مع خدمة عملاء ميدي لاب أو زيارة أقرب فرع للحصول على مساعدة مباشرة."
            if language == "ar"
            else "We could not determine your specific request after multiple attempts. Please contact MediLab customer service or visit your nearest branch for assistance."
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

    # Discover candidate options from the real catalog using the LLM-extracted query.
    # Candidate discovery is deterministic business-data lookup; natural-language understanding
    # remains the responsibility of the LLM request-understanding stage.
    options: list[str] = []
    snapshot_items: list[dict[str, Any]] = []

    entities = state.get("entities", {})
    query = entities.get("test_query") or state.get("normalized_user_message", "")

    test_repo = TestRepository()
    pkg_repo = PackageRepository()

    matched_tests = test_repo.search(query=query, active_only=True)
    matched_packages = pkg_repo.search(query=query, active_only=True)

    for test in matched_tests:
        options.append(f"{test.name} ({test.price} EGP)")
        snapshot_items.append(
            {
                "type": "test",
                "id": test.id,
                "code": test.code,
                "name": test.name,
                "price": str(test.price),
            }
        )
    for package in matched_packages:
        options.append(f"{package.name} ({package.price} EGP)")
        snapshot_items.append(
            {
                "type": "package",
                "id": package.id,
                "name": package.name,
                "price": str(package.price),
            }
        )

    # Save exactly the visible candidate set as the active SearchSnapshot.
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
        "snapshot_id": active_snapshot.get("id") if active_snapshot else None,
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
