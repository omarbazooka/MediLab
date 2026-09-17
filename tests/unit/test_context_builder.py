"""Unit tests for final context assembly and provenance formatting."""

from __future__ import annotations

from app.rag.context import build_retrieval_context
from app.rag.types import RetrievedChunk


def _chunk(chunk_id: int, content: str, title: str = "Doc") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=chunk_id,
        document_title=title,
        document_category="General",
        document_version=1,
        chunk_index=0,
        content=content,
        semantic_rank=1,
        rrf_score=0.03,
    )


def test_context_builder_caps_at_max_chunks() -> None:
    chunks = [_chunk(i, f"Unique passage content number {i}") for i in range(10)]
    ctx = build_retrieval_context(chunks, max_chunks=4)
    assert len(ctx.chunks) == 4
    assert len(ctx.sources) == 4
    assert "[Source 4:" in ctx.formatted_text
    assert "[Source 5:" not in ctx.formatted_text


def test_context_builder_deduplicates_identical_content() -> None:
    chunks = [
        _chunk(1, "Identical duplicate passage."),
        _chunk(2, "Identical duplicate passage.   "),
        _chunk(3, "Second unique passage."),
    ]
    ctx = build_retrieval_context(chunks, max_chunks=4)
    assert len(ctx.chunks) == 2
    assert ctx.chunks[0].chunk_id == 1
    assert ctx.chunks[1].chunk_id == 3


def test_context_builder_empty_pool() -> None:
    ctx = build_retrieval_context([])
    assert ctx.chunks == []
    assert ctx.sources == []
    assert ctx.formatted_text == ""
