"""Durable context persistence node saving turns and metadata to PostgreSQL."""

from __future__ import annotations

import time
from typing import Any

from app.agent.state import MediLabAgentState
from app.extensions import db
from app.models.snapshot import SearchSnapshot
from app.repositories.conversation_repository import ConversationRepository


def persist_context(state: MediLabAgentState) -> dict[str, Any]:
    """Persist conversation messages, structured state, and observability metadata to PostgreSQL."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    session_id = state["session_id"]
    user_msg = state.get("user_message", "")
    final_resp = state.get("final_response") or state.get("response_draft") or ""
    intent = state.get("intent")
    route_trace = state.get("route_trace", [])

    repo = ConversationRepository()
    session = repo.get_session(session_id)
    if session is None:
        session = repo.create_session(session_id=session_id)

    # 1. Persist User message
    repo.add_message(
        session_id=session_id,
        role="user",
        content=user_msg,
        intent=None,
        metadata_={},
    )

    # 2. Extract RAG chunk provenance for metadata (without unbounded blobs)
    rag_data = state.get("rag_result") or {}
    rag_chunks = rag_data.get("chunks", [])
    rag_metadata = [
        {
            "chunk_id": c.get("chunk_id"),
            "document_title": c.get("document_title"),
            "source_file": c.get("source_file"),
            "page": c.get("page_number"),
            "section": c.get("section_title"),
        }
        for c in rag_chunks[:4]
    ]

    timings["persist_context"] = (time.perf_counter() - t_start) * 1000
    total_ms = sum(timings.values())

    # Build bounded assistant metadata
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
        "node_timings_ms": {k: round(v, 2) for k, v in timings.items()},
        "total_latency_ms": round(total_ms, 2),
    }

    # 3. Persist Assistant message
    repo.add_message(
        session_id=session_id,
        role="assistant",
        content=final_resp,
        intent=intent,
        metadata_=assistant_metadata,
    )

    # 4. Update durable session state
    session.selected_test_id = state.get("selected_test_id")
    session.selected_package_id = state.get("selected_package_id")
    session.pending_clarification = state.get("pending_clarification")

    # Update active snapshot reference if set and valid for this session
    snap_data = state.get("active_search_snapshot")
    if snap_data and snap_data.get("id"):
        snap_id = snap_data["id"]
        # Verify snapshot exists and belongs to this session
        snap_row = db.session.get(SearchSnapshot, snap_id)
        if snap_row and snap_row.session_id == session_id:
            session.active_snapshot_id = snap_id

    # Update session current_state JSON
    curr_state = dict(session.current_state or {})
    curr_state["last_intent"] = intent
    curr_state["last_updated_turn"] = assistant_metadata["total_latency_ms"]
    if state.get("entities"):
        curr_state["last_entities"] = state["entities"]
    session.current_state = curr_state

    db.session.commit()

    return {
        "node_timings": timings,
        "total_latency_ms": total_ms,
    }
