"""Context resolution node for pending clarifications and visible references."""

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
    for word, pos in ORDINAL_WORDS_MAP.items():
        pattern = rf"(?:\b|(?<=[\u0600-\u06FF])){re.escape(word)}(?:\b|(?=[\u0600-\u06FF]))"
        if re.search(pattern, lower):
            return pos

    num_match = re.search(r"(?:number|no\.?|option|رقم|خيار)\s*([1-9])", lower)
    if num_match:
        return int(num_match.group(1))

    digit_match = re.search(r"\b([1-9])\b", lower)
    if digit_match:
        return int(digit_match.group(1))

    return None


def _item_id(item: dict[str, Any]) -> Any:
    return item.get("id") or item.get("entity_id")


def _infer_item_type(item: dict[str, Any]) -> str:
    explicit = item.get("type") or item.get("entity_type")
    if explicit:
        return str(explicit).lower()
    code_str = str(item.get("code", "")).lower()
    name_str = str(item.get("name", "")).lower()
    if "pkg" in code_str or "package" in name_str or "panel" in name_str or "باقة" in name_str:
        return "package"
    return "test"


def _snapshot_is_active(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot or not snapshot.get("items"):
        return False
    return str(snapshot.get("status", "ACTIVE")).upper() == "ACTIVE"


def resolve_pending_context(state: MediLabAgentState) -> dict[str, Any]:
    """Resolve pending clarification/reference state without allowing hidden candidate selection."""
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

    # An explicit catalog code may override an older selection when deterministic lookup
    # proves it exists. This is a new explicit choice, not an ordinal/snapshot inference.
    test_repo = TestRepository()
    query_entity = entities.get("test_query")
    if query_entity and isinstance(query_entity, str):
        found_test = test_repo.get_by_code(query_entity)
        if found_test:
            selected_test_id = found_test.id
            selected_package_id = None
            needs_clarification = False
            pending_clarification = None

    ordinal = entities.get("ordinal_ref") or _extract_ordinal_from_text(user_msg)
    proposed_visible_id = entities.get("visible_item_id")
    proposed_visible_type = entities.get("visible_item_type")

    if (ordinal or proposed_visible_id is not None) and _snapshot_is_active(active_snapshot):
        items: list[dict[str, Any]] = active_snapshot["items"]
        target_item: dict[str, Any] | None = None

        if ordinal:
            try:
                ordinal_pos = int(ordinal)
            except (TypeError, ValueError):
                ordinal_pos = 0
            for index, item in enumerate(items, start=1):
                stored_position = item.get("position", index)
                try:
                    visible_position = int(stored_position)
                except (TypeError, ValueError):
                    visible_position = index
                if visible_position == ordinal_pos:
                    target_item = item
                    break
        else:
            for item in items:
                same_id = str(_item_id(item)) == str(proposed_visible_id)
                same_type = (
                    proposed_visible_type is None
                    or _infer_item_type(item) == str(proposed_visible_type).lower()
                )
                if same_id and same_type:
                    target_item = item
                    break

        if target_item is not None:
            item_id = _item_id(target_item)
            item_type = _infer_item_type(target_item)
            if item_type == "package":
                selected_package_id = item_id
                selected_test_id = None
                entities["package_query"] = target_item.get("name")
            else:
                selected_test_id = item_id
                selected_package_id = None
                entities["test_query"] = target_item.get("name") or target_item.get("code")

            pending_clarification = None
            needs_clarification = False
        elif pending_clarification:
            needs_clarification = True
    elif (ordinal or proposed_visible_id is not None) and pending_clarification:
        # Missing or stale snapshots can never back a positional/semantic visible reference.
        needs_clarification = True

    if pending_clarification and not needs_clarification:
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
