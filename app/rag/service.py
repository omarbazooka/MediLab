"""Standalone hybrid RAG retrieval service orchestrating rewriting, retrieval, fusion, and grading."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.rag.context import build_retrieval_context
from app.rag.embeddings import EmbeddingProvider, JinaEmbeddingProvider
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.grading import grade_retrieval
from app.rag.rewrite import rewrite_query
from app.rag.types import (
    LexicalCandidate,
    RAGResult,
    RetrievalDiagnostics,
    RetrievalFilters,
    RetrievalOutcome,
    RetrievedChunk,
    SemanticCandidate,
)
from app.repositories.knowledge_repository import KnowledgeRepository

logger = logging.getLogger("medilab.rag.service")


class RAGRetrievalError(Exception):
    """Raised when both retrieval arms fail due to infrastructure or database errors."""


class RAGService:
    """Production-ready hybrid RAG retrieval pipeline operating independently of LangGraph."""

    def __init__(
        self,
        repository: KnowledgeRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        candidate_pool_size: int = 8,
        final_context_size: int = 4,
    ) -> None:
        self.repository = repository or KnowledgeRepository()
        self.embedding_provider = embedding_provider or JinaEmbeddingProvider()
        self.candidate_pool_size = candidate_pool_size
        self.final_context_size = final_context_size

    def _execute_hybrid_retrieval(
        self,
        search_query: str,
        filters: RetrievalFilters | None,
        diagnostics: RetrievalDiagnostics,
    ) -> tuple[list[RetrievedChunk], bool, str | None]:
        """Execute semantic + lexical retrieval with degraded mode recovery."""
        category = filters.category if filters else None
        doc_ids = filters.document_ids if filters else None

        semantic_candidates: list[SemanticCandidate] = []
        lexical_candidates: list[LexicalCandidate] = []
        semantic_failed = False
        lexical_failed = False
        degraded_reason: str | None = None

        # 1. Semantic retrieval arm
        t_embed_start = time.perf_counter()
        try:
            query_vec = self.embedding_provider.embed_query(search_query)
            diagnostics.embed_ms += (time.perf_counter() - t_embed_start) * 1000

            t_sem_start = time.perf_counter()
            semantic_candidates = self.repository.search_semantic(
                query_embedding=query_vec,
                top_k=self.candidate_pool_size,
                category=category,
                document_ids=doc_ids,
            )
            diagnostics.semantic_ms += (time.perf_counter() - t_sem_start) * 1000
            diagnostics.semantic_candidates_count = len(semantic_candidates)
        except Exception as exc:
            semantic_failed = True
            degraded_reason = f"Semantic retrieval failed: {type(exc).__name__}"
            logger.warning("Degraded mode: semantic search arm failed: %s", exc)

        # 2. Lexical retrieval arm
        t_lex_start = time.perf_counter()
        try:
            lexical_candidates = self.repository.search_lexical(
                query_text=search_query,
                top_k=self.candidate_pool_size,
                category=category,
                document_ids=doc_ids,
            )
            diagnostics.lexical_ms += (time.perf_counter() - t_lex_start) * 1000
            diagnostics.lexical_candidates_count = len(lexical_candidates)
        except Exception as exc:
            lexical_failed = True
            degraded_reason = f"Lexical retrieval failed: {type(exc).__name__}"
            logger.warning("Degraded mode: lexical search arm failed: %s", exc)

        # If both retrieval arms fail, this is an infrastructure failure, NOT NO_KNOWLEDGE
        if semantic_failed and lexical_failed:
            raise RAGRetrievalError(
                "Both semantic and lexical retrieval arms failed. RAG retrieval unavailable."
            )

        degraded = semantic_failed or lexical_failed

        # 3. Reciprocal Rank Fusion
        t_fuse_start = time.perf_counter()
        fused = reciprocal_rank_fusion(
            semantic_candidates=semantic_candidates,
            lexical_candidates=lexical_candidates,
        )
        diagnostics.fusion_ms += (time.perf_counter() - t_fuse_start) * 1000

        return fused, degraded, degraded_reason

    def _generate_alternate_query(self, query: str, resolved_entity: str | None) -> str:
        """Produce deterministic query variations for bounded retry."""
        if resolved_entity:
            return f"{resolved_entity} policy instructions details"

        # Strip common punctuation and filler words for a cleaner keyword query
        clean = query.replace("?", " ").replace("؟", " ").replace("!", " ").strip()
        words = clean.split()
        if len(words) > 3:
            # Drop very common leading question prefixes in English/Arabic
            drop_prefixes = {"what", "how", "can", "does", "is", "هل", "ما", "كيف", "ممكن"}
            filtered = [w for w in words if w.lower() not in drop_prefixes]
            if filtered:
                return " ".join(filtered)
        return clean

    def retrieve(
        self,
        query: str,
        context: dict[str, Any] | None = None,
        filters: RetrievalFilters | None = None,
    ) -> RAGResult:
        """Retrieve authoritative passages for user query with context-aware rewrite and bounded retry."""
        t_total_start = time.perf_counter()
        diagnostics = RetrievalDiagnostics()

        # Step 1: Context-aware query rewrite
        t_rw_start = time.perf_counter()
        rw_result = rewrite_query(query, context=context)
        diagnostics.rewrite_ms = (time.perf_counter() - t_rw_start) * 1000

        if rw_result.status == "AMBIGUOUS_USER_QUERY":
            diagnostics.total_ms = (time.perf_counter() - t_total_start) * 1000
            return RAGResult(
                original_query=query,
                rewritten_query=rw_result.rewritten_query,
                outcome=RetrievalOutcome.AMBIGUOUS_USER_QUERY.value,
                attempt_count=1,
                final_chunks=[],
                sources=[],
                context=None,
                diagnostics=diagnostics,
                degraded_mode=False,
                latency_ms=diagnostics.total_ms,
            )

        # Step 2: First retrieval attempt
        effective_query = rw_result.rewritten_query
        fused_chunks, degraded, deg_reason = self._execute_hybrid_retrieval(
            search_query=effective_query,
            filters=filters,
            diagnostics=diagnostics,
        )

        diagnostics.degraded_mode = degraded
        diagnostics.degraded_reason = deg_reason

        # Step 3: Grade initial retrieval
        t_grade_start = time.perf_counter()
        outcome = grade_retrieval(fused_chunks)
        diagnostics.grading_ms += (time.perf_counter() - t_grade_start) * 1000

        # Step 4: Bounded Retry (exactly ONE retry on WEAK_RETRY)
        if outcome == RetrievalOutcome.WEAK_RETRY:
            diagnostics.retry_used = True
            diagnostics.attempt_count = 2
            alternate_query = self._generate_alternate_query(
                query=effective_query,
                resolved_entity=rw_result.resolved_entity,
            )

            retry_chunks, retry_degraded, retry_deg_reason = self._execute_hybrid_retrieval(
                search_query=alternate_query,
                filters=filters,
                diagnostics=diagnostics,
            )

            if retry_degraded:
                diagnostics.degraded_mode = True
                diagnostics.degraded_reason = retry_deg_reason

            # Merge results preferring higher scoring candidates
            combined_pool = {c.chunk_id: c for c in retry_chunks}
            for c in fused_chunks:
                if c.chunk_id not in combined_pool:
                    combined_pool[c.chunk_id] = c
                else:
                    combined_pool[c.chunk_id].rrf_score = max(
                        combined_pool[c.chunk_id].rrf_score, c.rrf_score
                    )

            fused_chunks = sorted(
                combined_pool.values(),
                key=lambda ch: (-ch.rrf_score, ch.chunk_id),
            )

            t_regrade_start = time.perf_counter()
            outcome = grade_retrieval(fused_chunks)
            diagnostics.grading_ms += (time.perf_counter() - t_regrade_start) * 1000

        # Step 5: Final context assembly
        t_ctx_start = time.perf_counter()
        if outcome == RetrievalOutcome.NO_KNOWLEDGE:
            retrieval_ctx = None
            final_chunks: list[RetrievedChunk] = []
            sources: list[dict[str, Any]] = []
        else:
            retrieval_ctx = build_retrieval_context(
                fused_chunks=fused_chunks,
                max_chunks=self.final_context_size,
            )
            final_chunks = retrieval_ctx.chunks
            sources = retrieval_ctx.sources

        diagnostics.context_ms = (time.perf_counter() - t_ctx_start) * 1000
        diagnostics.total_ms = (time.perf_counter() - t_total_start) * 1000

        return RAGResult(
            original_query=query,
            rewritten_query=effective_query,
            outcome=outcome.value,
            attempt_count=diagnostics.attempt_count,
            final_chunks=final_chunks,
            sources=sources,
            context=retrieval_ctx,
            diagnostics=diagnostics,
            degraded_mode=diagnostics.degraded_mode,
            latency_ms=diagnostics.total_ms,
        )
