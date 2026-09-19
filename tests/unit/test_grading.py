"""Unit tests for signal-based retrieval grader."""

from __future__ import annotations

from app.rag.grading import grade_retrieval
from app.rag.types import RetrievalOutcome, RetrievedChunk


def _make_chunk(
    chunk_id: int = 1,
    semantic_rank: int | None = None,
    lexical_rank: int | None = None,
    cosine_distance: float | None = None,
    fts_score: float | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        document_title="Sample Doc",
        document_category="Policies",
        document_version=1,
        chunk_index=0,
        content="Sample content for testing grader.",
        semantic_rank=semantic_rank,
        lexical_rank=lexical_rank,
        cosine_distance=cosine_distance,
        fts_score=fts_score,
        rrf_score=0.03,
    )


def test_empty_chunks_returns_no_knowledge() -> None:
    outcome = grade_retrieval([])
    assert outcome == RetrievalOutcome.NO_KNOWLEDGE


def test_ambiguous_query_flag_returns_ambiguous_outcome() -> None:
    chunks = [_make_chunk(semantic_rank=1, cosine_distance=0.2)]
    outcome = grade_retrieval(chunks, is_ambiguous_query=True)
    assert outcome == RetrievalOutcome.AMBIGUOUS_USER_QUERY


def test_dual_arm_agreement_returns_good() -> None:
    chunk = _make_chunk(semantic_rank=1, lexical_rank=1, cosine_distance=0.35, fts_score=0.8)
    outcome = grade_retrieval([chunk])
    assert outcome == RetrievalOutcome.GOOD


def test_strong_semantic_distance_returns_good() -> None:
    chunk = _make_chunk(semantic_rank=1, cosine_distance=0.30)
    outcome = grade_retrieval([chunk])
    assert outcome == RetrievalOutcome.GOOD


def test_borderline_distance_returns_weak_retry() -> None:
    chunk = _make_chunk(semantic_rank=1, lexical_rank=2, cosine_distance=0.51, fts_score=0.08)
    outcome = grade_retrieval([chunk])
    assert outcome == RetrievalOutcome.WEAK_RETRY


def test_high_noise_distance_returns_no_knowledge() -> None:
    chunk = _make_chunk(semantic_rank=1, cosine_distance=0.68)
    outcome = grade_retrieval([chunk])
    assert outcome == RetrievalOutcome.NO_KNOWLEDGE
