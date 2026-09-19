"""RAG node executing Phase 2 hybrid retrieval with conversational entity conditioning."""

from __future__ import annotations

import time
from typing import Any

from app.agent.state import MediLabAgentState
from app.rag.service import RAGService
from app.repositories.test_repository import TestRepository


def rag_node(state: MediLabAgentState) -> dict[str, Any]:
    """Execute hybrid RAG retrieval against authoritative MediLab PDF knowledge corpus."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("rag_node")

    rag_service = RAGService()
    test_repo = TestRepository()

    # Build context for query rewriting
    context: dict[str, Any] = {}
    selected_test_id = state.get("selected_test_id")
    if selected_test_id:
        test_obj = test_repo.get_by_id(selected_test_id)
        if test_obj:
            context["selected_test"] = test_obj.name
            context["selected_test_name"] = test_obj.name
            context["current_subject"] = test_obj.name
            context["selected_code"] = test_obj.code
    elif state.get("entities", {}).get("test_query"):
        q_entity = str(state["entities"]["test_query"])
        context["selected_test"] = q_entity
        context["selected_test_name"] = q_entity
        context["current_subject"] = q_entity

    query = state.get("normalized_user_message") or state.get("user_message", "")

    try:
        retrieval = rag_service.retrieve(query=query, context=context)
        chunks_data = [
            {
                "chunk_id": c.chunk_id,
                "content": c.content,
                "document_title": c.document_title,
                "source_file": c.source_file,
                "page_number": c.page_start,
                "section_title": c.section_title,
                "score": c.rrf_score,
            }
            for c in retrieval.final_chunks
        ]
        rag_payload = {
            "outcome": retrieval.outcome,
            "chunks": chunks_data,
            "sources": retrieval.sources,
            "rewritten_query": retrieval.rewritten_query,
            "degraded_mode": retrieval.degraded_mode,
        }
    except Exception as exc:
        rag_payload = {
            "outcome": "NO_KNOWLEDGE",
            "chunks": [],
            "sources": [],
            "error": str(exc),
        }

    timings["rag_node"] = (time.perf_counter() - t_start) * 1000

    result: dict[str, Any] = {
        "rag_result": rag_payload,
        "route_trace": routes,
        "node_timings": timings,
    }

    if rag_payload.get("outcome") == "NO_KNOWLEDGE":
        result["response_goal"] = "NO_KNOWLEDGE"

    return result
