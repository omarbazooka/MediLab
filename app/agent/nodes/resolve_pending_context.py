"""Context resolution node for pending clarifications and visible ordinal references."""

from __future__ import annotations

import re
import time
from typing import Any

from app.agent.state import MediLabAgentState
from app.repositories.test_repository import TestRepository

ORDINAL_WORDS_MAP: dict[str, int] = {
    "first": 1,
    "1st": 1,
    "الأول": 1,
    "الاول": 1,
    "١": 1,
    "second": 2,
    "2nd": 2,
    "الثاني": 2,
    "التاني": 2,
    "٢": 2,
    "third": 3,
    "3rd": 3,
    "الثالث": 3,
    "التالت": 3,
    "٣": 3,
    "fourth": 4,
    "4th": 4,
    "الرابع": 4,
    "٤": 4,
    "fifth": 5,
    "5th": 5,
    "الخامس": 5,
    "٥": 5,
}


def _extract_ordinal_from_text(text: str) -> int | None:
    """Extract 1-based ordinal position from English or Arabic phrasing."""
    lower = text.lower()
    # Check specific ordinal words first (second, third, first, etc.)
    for word, pos in ORDINAL_WORDS_MAP.items():
        pattern = rf"(?:\b|(?<=[\u0600-\u06FF])){re.escape(word)}(?:\b|(?=[\u0600-\u06FF]))"
        if re.search(pattern, lower):
            return pos

    # Check for "رقم 2" or "number 2" or "option 2"
    num_match = re.search(r"(?:number|no\.?|option|رقم|خيار)\s*([1-9])", lower)
    if num_match:
        return int(num_match.group(1))

    # Check standalone digits " 1 ", " 2 ", " 3 "
    digit_match = re.search(r"\b([1-9])\b", lower)
    if digit_match:
        return int(digit_match.group(1))

    return None


def resolve_pending_context(state: MediLabAgentState) -> dict[str, Any]:
    """Resolve pending clarification, ordinal references against visible SearchSnapshot, and explicit corrections."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    if not state.get("is_safe", True):
        timings["resolve_pending_context"] = (time.perf_counter() - t_start) * 1000
        return {"node_timings": timings}

    user_msg = state.get("normalized_user_message") or state.get("user_message", "")
    entities = dict(state.get("entities", {}))
    pending_clarification = state.get("pending_clarification")
    active_snapshot = state.get("active_search_snapshot")
    selected_test_id = state.get("selected_test_id")
    selected_package_id = state.get("selected_package_id")
    needs_clarification = state.get("needs_clarification", False)

    # 1. Explicit user override: check if user explicitly mentions a different test code
    test_repo = TestRepository()
    query_entity = entities.get("test_query")
    if query_entity and isinstance(query_entity, str):
        found_test = test_repo.get_by_code(query_entity)
        if found_test:
            # Explicit statement overrides previous selection
            selected_test_id = found_test.id
            selected_package_id = None
            needs_clarification = False
            pending_clarification = None

    # 2. Ordinal resolution against active SearchSnapshot
    ordinal = entities.get("ordinal_ref")
    if not ordinal:
        ordinal = _extract_ordinal_from_text(user_msg)

    # Check for keywords like "the full one" or "الباقة" when choosing between options
    is_full_option = any(
        w in user_msg.lower() for w in ["full", "الكامل", "الكاملة", "باقة", "panel"]
    )

    if (ordinal or is_full_option) and active_snapshot and active_snapshot.get("items"):
        items = active_snapshot["items"]
        target_item = None

        if is_full_option:
            # Strictly match against visible items that are actually packages or panels
            for it in items:
                it_name = str(it.get("name", "")).lower()
                it_type = str(it.get("type", "")).lower()
                if it_type == "package" or any(
                    k in it_name for k in ["panel", "package", "باقة", "شامل", "كامل"]
                ):
                    target_item = it
                    break
        elif ordinal and 1 <= ordinal <= len(items):
            target_item = items[ordinal - 1]

        # Verify candidate is genuinely part of the visible snapshot
        visible_ids = {it.get("id") or it.get("entity_id") for it in items}
        if target_item and (target_item.get("id") or target_item.get("entity_id")) in visible_ids:
            item_id = target_item.get("id") or target_item.get("entity_id")
            item_type = target_item.get("type") or target_item.get("entity_type")
            if not item_type:
                code_str = str(target_item.get("code", "")).lower()
                name_str = str(target_item.get("name", "")).lower()
                if (
                    "pkg" in code_str
                    or "package" in name_str
                    or "panel" in name_str
                    or "باقة" in name_str
                ):
                    item_type = "package"
                else:
                    item_type = "test"

            if item_type == "package":
                selected_package_id = item_id
                selected_test_id = None
                entities["package_query"] = target_item.get("name")
            else:
                selected_test_id = item_id
                selected_package_id = None
                entities["test_query"] = target_item.get("name") or target_item.get("code")

            # Successfully resolved pending choice from visible snapshot!
            pending_clarification = None
            needs_clarification = False

    # 3. If pending clarification was active and user provided a resolving answer
    if pending_clarification and not needs_clarification:
        # Clarification was resolved in this turn
        pending_clarification = None

    timings["resolve_pending_context"] = (time.perf_counter() - t_start) * 1000

    return {
        "selected_test_id": selected_test_id,
        "selected_package_id": selected_package_id,
        "pending_clarification": pending_clarification,
        "needs_clarification": needs_clarification,
        "entities": entities,
        "node_timings": timings,
    }
