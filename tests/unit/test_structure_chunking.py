"""Unit tests for structure-aware PDF chunking."""

from __future__ import annotations

from app.rag.chunking import (
    chunk_parsed_document,
)
from app.rag.parsers.pdf import ParsedDocument, ParsedSection


def create_mock_parsed_document() -> ParsedDocument:
    """Helper creating a multi-section ParsedDocument."""
    s1 = ParsedSection(
        title="1. Fasting Instructions",
        section_number="1",
        content=(
            "For a complete lipid panel, the patient must fast for 10 to 12 hours. "
            "Only plain water is permitted during this preparation window. "
            "Do not consume tea, coffee, milk, or juices."
        ),
        page_start=1,
        page_end=1,
    )
    s2 = ParsedSection(
        title="2. Privacy and Identification",
        section_number="2",
        content=(
            "Patient identity must be confirmed using at least two independent identifiers. "
            "Results will only be released to the patient or authorized representatives. "
            "MediLab enforces strict confidentiality under applicable data privacy laws."
        ),
        page_start=2,
        page_end=2,
    )
    return ParsedDocument(
        source_file="test_guide.pdf",
        title="Diagnostic Testing Guidelines",
        total_pages=2,
        sections=[s1, s2],
        raw_text=f"{s1.content}\n\n{s2.content}",
        file_hash="mock_hash_1234567890abcdef",
    )


def test_chunk_parsed_document_preserves_section_boundaries():
    """Verify that chunks never blend text from distinct sections."""
    doc = create_mock_parsed_document()
    chunks = chunk_parsed_document(doc, document_id=10, document_version=1, category="Policies")

    assert len(chunks) == 2
    c1, c2 = chunks[0], chunks[1]

    # Chunk 1 must only contain Fasting content
    assert "lipid panel" in c1["content"]
    assert "confidentiality" not in c1["content"]
    assert c1["metadata"]["section_title"] == "1. Fasting Instructions"
    assert c1["metadata"]["page_start"] == 1

    # Chunk 2 must only contain Privacy content
    assert "confidentiality" in c2["content"]
    assert "lipid panel" not in c2["content"]
    assert c2["metadata"]["section_title"] == "2. Privacy and Identification"
    assert c2["metadata"]["page_start"] == 2


def test_chunk_parsed_document_metadata_provenance():
    """Verify all required provenance metadata fields are populated."""
    doc = create_mock_parsed_document()
    chunks = chunk_parsed_document(doc, document_id=42, document_version=3, category="Preparation")

    for idx, c in enumerate(chunks):
        meta = c["metadata"]
        assert meta["document_id"] == 42
        assert meta["document_version"] == 3
        assert meta["title"] == "Diagnostic Testing Guidelines"
        assert meta["category"] == "Preparation"
        assert meta["source_file"] == "test_guide.pdf"
        assert meta["source_type"] == "pdf"
        assert meta["chunk_index"] == idx
        assert meta["content_hash"] == "mock_hash_1234567890abcdef"
        assert meta["char_count"] == len(c["content"])
        assert meta["word_count"] == len(c["content"].split())


def test_chunk_parsed_document_splits_oversized_section():
    """Verify that oversized sections are recursively split within the section boundary."""
    long_body = "This is a detailed paragraph explaining preparation steps in depth. " * 50
    assert len(long_body) > 1400

    s = ParsedSection(
        title="3. Long Section",
        section_number="3",
        content=long_body,
        page_start=3,
        page_end=4,
    )
    doc = ParsedDocument(
        source_file="oversized.pdf",
        title="Oversized Doc",
        total_pages=4,
        sections=[s],
        raw_text=long_body,
        file_hash="hash_oversized",
    )

    chunks = chunk_parsed_document(
        doc,
        document_id=1,
        document_version=1,
        category="General",
        chunk_size=1000,
        chunk_overlap=150,
    )

    # Must produce multiple sub-chunks
    assert len(chunks) > 1
    for c in chunks:
        assert len(c["content"]) <= 1100  # Within bounded split size
        assert c["metadata"]["section_title"] == "3. Long Section"
        assert c["metadata"]["page_start"] == 3
        assert c["metadata"]["page_end"] == 4


def test_chunk_parsed_document_arabic_support():
    """Verify structure-aware chunking supports Arabic text and punctuation."""
    ar_content = (
        "تحليل السكر الصائم يتطلب الامتناع عن تناول الأطعمة والمشروبات لمدة 8 ساعات قبل سحب العينة. "
        "يسمح فقط بتناول الماء النقي بكميات معتدلة. "
        "في حالة تناول أي طعام بالخطأ، يرجى إبلاغ موظف الاستقبال لتحديد موعد بديل."
    )
    s = ParsedSection(
        title="1. إرشادات الصيام",
        section_number="1",
        content=ar_content,
        page_start=1,
        page_end=1,
    )
    doc = ParsedDocument(
        source_file="arabic_guide.pdf",
        title="دليل التحاليل الطبية",
        total_pages=1,
        sections=[s],
        raw_text=ar_content,
        file_hash="arabic_hash_123",
    )

    chunks = chunk_parsed_document(doc, document_id=5, document_version=1, category="Preparation")
    assert len(chunks) == 1
    assert "تحليل السكر الصائم" in chunks[0]["content"]
    assert chunks[0]["metadata"]["section_title"] == "1. إرشادات الصيام"
    assert chunks[0]["metadata"]["source_type"] == "pdf"
