"""Unit tests for Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

from app.rag.fusion import reciprocal_rank_fusion
from app.rag.types import LexicalCandidate, SemanticCandidate


def _make_semantic_cand(chunk_id: int, dist: float = 0.2) -> SemanticCandidate:
    return SemanticCandidate(
        chunk_id=chunk_id,
        document_id=1,
        document_title="Doc 1",
        document_category="Preparation",
        document_version=1,
        chunk_index=0,
        content=f"Content for chunk {chunk_id}",
        cosine_distance=dist,
        semantic_rank=1,
    )


def _make_lexical_cand(chunk_id: int, score: float = 0.5) -> LexicalCandidate:
    return LexicalCandidate(
        chunk_id=chunk_id,
        document_id=1,
        document_title="Doc 1",
        document_category="Preparation",
        document_version=1,
        chunk_index=0,
        content=f"Content for chunk {chunk_id}",
        fts_score=score,
        lexical_rank=1,
    )


def test_rrf_semantic_only() -> None:
    sem = [_make_semantic_cand(10), _make_semantic_cand(20)]
    fused = reciprocal_rank_fusion(sem, [])
    assert len(fused) == 2
    assert fused[0].chunk_id == 10
    assert fused[0].semantic_rank == 1
    assert fused[0].lexical_rank is None
    assert fused[1].chunk_id == 20
    assert fused[1].semantic_rank == 2
    assert fused[0].rrf_score > fused[1].rrf_score


def test_rrf_lexical_only() -> None:
    lex = [_make_lexical_cand(100), _make_lexical_cand(200)]
    fused = reciprocal_rank_fusion([], lex)
    assert len(fused) == 2
    assert fused[0].chunk_id == 100
    assert fused[0].lexical_rank == 1
    assert fused[0].semantic_rank is None
    assert fused[1].chunk_id == 200
    assert fused[1].lexical_rank == 2


def test_rrf_overlap_boosts_chunk_score() -> None:
    # Chunk 1 is rank 2 in semantic and rank 2 in lexical.
    # Chunk 2 is rank 1 in semantic only.
    # Chunk 3 is rank 1 in lexical only.
    # Formula:
    # Chunk 1: 1/(60+2) + 1/(60+2) = 2/62 ≈ 0.032258
    # Chunk 2: 1/(60+1) = 1/61 ≈ 0.016393
    # Chunk 3: 1/(60+1) = 1/61 ≈ 0.016393
    # Therefore, Chunk 1 with dual-arm presence MUST rank #1!
    sem = [_make_semantic_cand(2), _make_semantic_cand(1)]
    lex = [_make_lexical_cand(3), _make_lexical_cand(1)]

    fused = reciprocal_rank_fusion(sem, lex, k=60)
    assert len(fused) == 3
    assert fused[0].chunk_id == 1
    assert fused[0].semantic_rank == 2
    assert fused[0].lexical_rank == 2
    assert fused[0].rrf_score > fused[1].rrf_score


def test_rrf_deduplicates_chunks() -> None:
    sem = [_make_semantic_cand(5)]
    lex = [_make_lexical_cand(5)]
    fused = reciprocal_rank_fusion(sem, lex)
    assert len(fused) == 1
    assert fused[0].chunk_id == 5
    assert fused[0].semantic_rank == 1
    assert fused[0].lexical_rank == 1
