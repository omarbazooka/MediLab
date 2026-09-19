"""Durable context persistence node saving turns and metadata to PostgreSQL."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from app.agent.nodes.input_guard import SESSION_ID_PATTERN
from app.agent.state import MediLabAgentState
from app.extensions import db
from app.models.snapshot import SearchSnapshot
from app.repositories.conversation_repository import ConversationRepository


def persist_context(state: MediLabAgentState) -> dict[str, Any]:
    """Persist a valid conversation turn and bounded observability metadata to PostgreSQL."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    session_id = (state.get("session_id") or "").strip()

    # input_guard may intentionally terminate a malformed request before a durable session
    # exists. Never create invalid session identifiers as a side effect of error persistence.
    if not session_id or not SESSION_ID_PATTERN.fullmatch(session_id):
        timings["persist_context"] = (time.perf_counter() - t_start) * 1000
        return {
            "node_timings": timings,
            "total_latency_ms": sum(timings.values()),
        }

    user_msg = state.get("user_message", "")
    final_resp = state.get("final_response") or state.get("response_draft") or ""
    intent = state.get("intent")
    route_trace = state.get("route_trace", [])

    repo = ConversationRepository()
    session = repo.get_session(session_id)
    if session is None:
        session = repo.create_session(session_id=session_id)

    repo.add_message(
        session_id=session_id,
        role="user",
        content=user_msg,
        intent=None,
        metadata_={},
    )

    rag_data = state.get("rag_result") or {}
    rag_chunks = rag_data.get("chunks", [])
    rag_metadata = [
        {
            "chunk_id": chunk.get("chunk_id"),
            "document_title": chunk.get("document_title"),
            "source_file": chunk.get("source_file"),
            "page": chunk.get("page_number"),
            "section": chunk.get("section_title"),
        }
        for chunk in rag_chunks[:4]
    ]

    timings["persist_context"] = (time.perf_counter() - t_start) * 1000
    total_ms = sum(timings.values())

    assistant_metadata = {
        "intent": intent,
        "route_trace": route_trace,
        "safety": state.get("safety_classification"),
        "selected_test_id": state.get("selected_test_id"),
        "selected_package_id": state.get("selected_package_id"),
        "response_goal": state.get("response_goal"),
        "clarification_target": state.get("clarification_target"),
        "clarification_attempts": state.get("clarification_attempts", 0),
        "validation": state.get("validation_result"),
        "rag_sources": rag_metadata,
        "node_timings_ms": {key: round(value, 2) for key, value in timings.items()},
        "total_latency_ms": round(total_ms, 2),
    }

    repo.add_message(
        session_id=session_id,
        role="assistant",
        content=final_resp,
        intent=intent,
        metadata_=assistant_metadata,
    )

    session.selected_test_id = state.get("selected_test_id")
    session.selected_package_id = state.get("selected_package_id")
    session.pending_clarification = state.get("pending_clarification")
    session.pending_action = state.get("pending_action")

    snap_data = state.get("active_search_snapshot")
    if (
        snap_data
        and snap_data.get("id")
        and str(snap_data.get("status", "ACTIVE")).upper() == "ACTIVE"
    ):
        snap_id = snap_data["id"]
        snap_row = db.session.get(SearchSnapshot, snap_id)
        if snap_row and snap_row.session_id == session_id and snap_row.status == "ACTIVE":
            session.active_snapshot_id = snap_id

    curr_state = dict(session.current_state or {})
    curr_state["last_intent"] = intent
    curr_state["last_updated_at"] = datetime.now(UTC).isoformat()
    curr_state["last_turn_latency_ms"] = round(total_ms, 2)
    if state.get("entities"):
        curr_state["last_entities"] = state["entities"]
    session.current_state = curr_state

    db.session.commit()

    return {
        "node_timings": timings,
        "total_latency_ms": total_ms,
    }
