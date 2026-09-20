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
    """Generate one focused question and persist the exact visible candidate set."""
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

    options: list[str] = []
    snapshot_items: list[dict[str, Any]] = []

    entities = state.get("entities", {})
    query = (entities.get("test_query") or entities.get("package_query") or "").strip()
    if not query:
        raw = state.get("normalized_user_message", "")
        for kw in (
            "thyroid",
            "diabetes",
            "lipid",
            "cholesterol",
            "liver",
            "kidney",
            "urine",
            "blood",
            "cbc",
            "tsh",
            "kft",
            "lft",
            "vitd",
            "ferritin",
            "fbs",
            "hba1c",
        ):
            if kw in raw.lower():
                query = kw
                break
        if not query:
            query = raw

    test_repo = TestRepository()
    package_repo = PackageRepository()
    matched_tests = test_repo.search(query=query, active_only=True)
    matched_packages = package_repo.search(query=query, active_only=True)

    for test in matched_tests:
        position = len(snapshot_items) + 1
        label = f"{test.name} ({test.price} EGP)"
        options.append(label)
        snapshot_items.append(
            {
                "position": position,
                "type": "test",
                "id": test.id,
                "code": test.code,
                "name": test.name,
                "price": str(test.price),
            }
        )
    for package in matched_packages:
        position = len(snapshot_items) + 1
        label = f"{package.name} ({package.price} EGP)"
        options.append(label)
        snapshot_items.append(
            {
                "position": position,
                "type": "package",
                "id": package.id,
                "name": package.name,
                "price": str(package.price),
            }
        )

    active_snapshot = state.get("active_search_snapshot")
    if snapshot_items:
        conv_repo = ConversationRepository()
        seq = 1
        if active_snapshot:
            seq = active_snapshot.get("sequence_no", 0) + 1
        created_snapshot = conv_repo.save_snapshot(
            session_id=session_id,
            sequence_no=seq,
            query=query,
            criteria={"target": target},
            items=snapshot_items,
        )
        active_snapshot = {
            "id": created_snapshot.id,
            "sequence_no": created_snapshot.sequence_no,
            "query": created_snapshot.query,
            "status": created_snapshot.status,
            "items": created_snapshot.items,
        }

    provider = get_llm_provider()
    question = provider.generate_clarification(
        target=target,
        reason=reason,
        options=options,
        language=language,
    ).strip()

    # The LLM owns the natural question wording. Python renders the exact numbered
    # business options in the exact SearchSnapshot order so ordinal references always
    # correspond to what the customer actually saw.
    if options:
        numbered_options = "\n".join(
            f"{position}. {label}" for position, label in enumerate(options, start=1)
        )
        question = f"{question}\n{numbered_options}"

    pending_clarification_data = {
        "target": target,
        "attempts": attempts,
        "options": options,
        "visible_items": [
            {
                "position": item.get("position"),
                "type": item.get("type"),
                "id": item.get("id"),
                "code": item.get("code"),
                "name": item.get("name"),
            }
            for item in snapshot_items
        ],
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
