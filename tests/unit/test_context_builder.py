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


def test_context_builder_enforces_word_budget() -> None:
    passage_50_words = " ".join(["word"] * 50)
    chunks = [
        _chunk(1, passage_50_words),
        _chunk(2, passage_50_words),
        _chunk(3, passage_50_words),
    ]
    # Budget of 75 words allows chunk 1 (50 words), but rejects chunk 2 (would be 100 words)
    ctx = build_retrieval_context(chunks, max_chunks=4, max_words=75)
    assert len(ctx.chunks) == 1
    assert ctx.chunks[0].chunk_id == 1
    # Ensure text is complete and never chopped/truncated midway
    assert ctx.chunks[0].content == passage_50_words


def test_context_builder_never_returns_partial_fabricated_text() -> None:
    complete_sentence = "This is a full diagnostic instruction sentence that must never be chopped."
    chunks = [
        _chunk(1, complete_sentence),
        _chunk(2, "Second complete instruction sentence."),
    ]
    # Even with small word budget, first chunk is intact and not sliced into invalid syntax
    ctx = build_retrieval_context(chunks, max_chunks=4, max_words=15)
    assert len(ctx.chunks) == 1
    assert ctx.chunks[0].content == complete_sentence
    assert ctx.chunks[0].content.endswith("never be chopped.")


def test_context_builder_enforces_character_budget() -> None:
    chunk1 = _chunk(1, "A" * 200)
    chunk2 = _chunk(2, "B" * 200)
    ctx = build_retrieval_context([chunk1, chunk2], max_chars=250)
    assert len(ctx.chunks) == 1
    assert ctx.chunks[0].chunk_id == 1
