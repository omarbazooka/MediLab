"""RAG node executing Phase 2 hybrid retrieval with conversational entity conditioning."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent.state import MediLabAgentState
from app.rag.service import RAGService
from app.repositories.test_repository import TestRepository

logger = logging.getLogger("medilab.agent.rag")


def _controlled_rag_error(language: str) -> str:
    return (
        "عذراً، تعذر الوصول إلى قاعدة معلومات ميدي لاب حالياً. يرجى إعادة المحاولة بعد قليل."
        if language == "ar"
        else "I’m sorry, MediLab’s knowledge service is temporarily unavailable. Please try again shortly."
    )


def rag_node(state: MediLabAgentState) -> dict[str, Any]:
    """Execute hybrid RAG retrieval against authoritative MediLab PDF knowledge corpus."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    routes = list(state.get("route_trace", []))
    routes.append("rag_node")

    rag_service = RAGService()
    test_repo = TestRepository()

    context: dict[str, Any] = {}
    selected_test_id = state.get("selected_test_id")
    selected_package_id = state.get("selected_package_id")
    if selected_test_id:
        test_obj = test_repo.get_by_id(selected_test_id)
        if test_obj:
            context["selected_test"] = test_obj.name
            context["selected_test_name"] = test_obj.name
            context["current_subject"] = test_obj.name
            context["selected_code"] = test_obj.code
    elif selected_package_id:
        from app.repositories.package_repository import PackageRepository

        package_obj = PackageRepository().get_by_id(selected_package_id)
        if package_obj:
            context["selected_package"] = package_obj.name
            context["selected_package_name"] = package_obj.name
            context["current_subject"] = package_obj.name
    elif state.get("entities", {}).get("test_query"):
        query_entity = str(state["entities"]["test_query"])
        context["selected_test"] = query_entity
        context["selected_test_name"] = query_entity
        context["current_subject"] = query_entity

    query = state.get("normalized_user_message") or state.get("user_message", "")

    try:
        retrieval = rag_service.retrieve(query=query, context=context)
        chunks_data = [
            {
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "document_title": chunk.document_title,
                "source_file": chunk.source_file,
                "page_number": chunk.page_start,
                "section_title": chunk.section_title,
                "score": chunk.rrf_score,
            }
            for chunk in retrieval.final_chunks
        ]
        rag_payload = {
            "outcome": retrieval.outcome,
            "chunks": chunks_data,
            "sources": retrieval.sources,
            "rewritten_query": retrieval.rewritten_query,
            "degraded_mode": retrieval.degraded_mode,
        }
    except Exception:
        # Infrastructure/provider failure is not the same as an evidence-backed NO_KNOWLEDGE result.
        # Do not persist raw exception text; underlying services own sanitized internal logging.
        logger.error("RAG retrieval failed; returning controlled retrieval-unavailable state.")
        rag_payload = {
            "outcome": "RETRIEVAL_ERROR",
            "chunks": [],
            "sources": [],
            "error_code": "retrieval_unavailable",
        }

    timings["rag_node"] = (time.perf_counter() - t_start) * 1000

    result: dict[str, Any] = {
        "rag_result": rag_payload,
        "route_trace": routes,
        "node_timings": timings,
    }

    if rag_payload.get("outcome") == "NO_KNOWLEDGE":
        result["response_goal"] = "NO_KNOWLEDGE"
    elif rag_payload.get("outcome") == "RETRIEVAL_ERROR":
        language = state.get("language", "en")
        fallback = _controlled_rag_error(language)
        result.update(
            {
                "response_goal": "CONTROLLED_ERROR",
                "response_draft": fallback,
                "final_response": fallback,
                "controlled_errors": list(state.get("controlled_errors", []))
                + ["RAG retrieval unavailable."],
            }
        )

    return result
