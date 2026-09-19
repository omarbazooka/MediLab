"""Unit tests for deterministic text chunking."""

from __future__ import annotations

from app.rag.chunking import chunk_document, chunk_text


def test_short_document_remains_single_chunk() -> None:
    text = "Fasting is required for FBS test for 8 hours. Water is permitted."
    chunks = chunk_text(text, max_words=180, overlap_words=30)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunking_is_deterministic() -> None:
    text = (
        "Paragraph 1 contains general instructions for medical laboratory appointments.\n\n"
        "Paragraph 2 explains fasting requirements in full detail. " * 15
    )
    chunks_1 = chunk_text(text, max_words=50, overlap_words=10)
    chunks_2 = chunk_text(text, max_words=50, overlap_words=10)
    assert chunks_1 == chunks_2
    assert len(chunks_1) > 1


def test_stable_chunk_indices_and_metadata() -> None:
    content = "Sentence one. " * 30 + "\n\n" + "Sentence two. " * 30
    specs = chunk_document(
        content=content,
        document_id=42,
        document_version=3,
        title="Preparation Guide",
        category="Preparation",
        max_words=40,
        overlap_words=10,
    )
    assert len(specs) > 1
    for idx, spec in enumerate(specs):
        assert spec["chunk_index"] == idx
        assert spec["content"]
        meta = spec["metadata"]
        assert meta["document_id"] == 42
        assert meta["document_version"] == 3
        assert meta["title"] == "Preparation Guide"
        assert meta["category"] == "Preparation"
        assert meta["chunk_index"] == idx
        assert meta["word_count"] > 0


def test_no_empty_chunks() -> None:
    content = "   \n\n   \n   "
    chunks = chunk_text(content)
    assert chunks == []


def test_arabic_text_chunking() -> None:
    arabic_content = (
        "تعليمات الصيام للتحاليل الطبية: لتحليل السكر الصائم يلزم الصيام لمدة 8 ساعات كاملة.\n\n"
        "يسمح فقط بشرب الماء خلال فترة الصيام، ويمتنع المريض تماماً عن التدخين والمشروبات الأخرى.\n\n"
        "تحليل الدهون الكامل يتطلب صياماً من 10 إلى 12 ساعة متواصلة لضمان دقة النتائج المعملية."
    )
    chunks = chunk_text(arabic_content, max_words=15, overlap_words=4)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.strip()) > 0
        assert "الصيام" in arabic_content
