"""Pure, deterministic Reciprocal Rank Fusion (RRF) implementation."""

from __future__ import annotations

from app.rag.types import LexicalCandidate, RetrievedChunk, SemanticCandidate

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    semantic_candidates: list[SemanticCandidate],
    lexical_candidates: list[LexicalCandidate],
    k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """Fuse semantic and lexical retrieval candidates using Reciprocal Rank Fusion.

    Formula:
        RRF Score = Σ (1 / (k + rank))

    - Ranks are 1-based.
    - Chunks appearing in both result lists receive reinforced scores.
    - Tie-breaking is deterministic (descending RRF score, then ascending chunk_id).
    """
    merged: dict[int, RetrievedChunk] = {}

    # 1. Ingest semantic candidates
    for rank, sc in enumerate(semantic_candidates, start=1):
        score = 1.0 / (k + rank)
        merged[sc.chunk_id] = RetrievedChunk(
            chunk_id=sc.chunk_id,
            document_id=sc.document_id,
            document_title=sc.document_title,
            document_category=sc.document_category,
            document_version=sc.document_version,
            chunk_index=sc.chunk_index,
            content=sc.content,
            semantic_rank=rank,
            cosine_distance=sc.cosine_distance,
            rrf_score=score,
        )

    # 2. Ingest lexical candidates and fuse
    for rank, lc in enumerate(lexical_candidates, start=1):
        score = 1.0 / (k + rank)
        if lc.chunk_id in merged:
            chunk = merged[lc.chunk_id]
            chunk.lexical_rank = rank
            chunk.fts_score = lc.fts_score
            chunk.rrf_score += score
        else:
            merged[lc.chunk_id] = RetrievedChunk(
                chunk_id=lc.chunk_id,
                document_id=lc.document_id,
                document_title=lc.document_title,
                document_category=lc.document_category,
                document_version=lc.document_version,
                chunk_index=lc.chunk_index,
                content=lc.content,
                lexical_rank=rank,
                fts_score=lc.fts_score,
                rrf_score=score,
            )

    # Deterministic sort: descending RRF score, ascending chunk_id for tie-breaking
    sorted_chunks = sorted(
        merged.values(),
        key=lambda chunk: (-chunk.rrf_score, chunk.chunk_id),
    )

    return sorted_chunks
