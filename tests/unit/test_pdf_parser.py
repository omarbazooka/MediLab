"""Unit tests for structure-aware PyMuPDF PDF parser."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.rag.parsers.pdf import (
    ParsedDocument,
    PdfParser,
    PdfParsingError,
)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a multi-page valid PDF fixture with numbered headings."""
    pdf_path = tmp_path / "sample_guide.pdf"
    doc = fitz.open()

    # Page 1: Cover and overview
    p1 = doc.new_page()
    p1.insert_text(
        (50, 72),
        "MediLab AI Assessment - Knowledge Base Document - Version 1.0\n\n"
        "MEDILAB\n\n"
        "Specimen Transport & Storage\n\n"
        "Guide\n\n"
        "Knowledge Base Category: Processes\n\n"
        "This guide explains operational procedures for sample transport.",
    )

    # Page 2: Sections 1 and 2
    p2 = doc.new_page()
    p2.insert_text(
        (50, 72),
        "MediLab AI Assessment - Knowledge Base Document - Version 1.0\n\n"
        "Quick Reference\n"
        "Summary guidelines for cold chain compliance.\n\n"
        "1. Purpose and Scope\n"
        "All biological specimens must be transported according to temperature standards.\n\n"
        "2. Temperature Categories\n"
        "Samples must be stored at ambient (15-25C), refrigerated (2-8C), or frozen (-20C).",
    )

    # Page 3: Section 3 and Control Notes
    p3 = doc.new_page()
    p3.insert_text(
        (50, 72),
        "MediLab AI Assessment - Knowledge Base Document - Version 1.0\n\n"
        "3. Recollection Policy\n"
        "If temperature deviation exceeds 2 hours, a recollection must be triggered immediately.\n\n"
        "Document Control Notes\n"
        "Document reference: MLB-SOP-005.",
    )

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_pdf_parser_valid_extraction(sample_pdf: Path):
    """Test full parsing of a valid multi-page PDF."""
    parser = PdfParser()
    parsed = parser.parse(sample_pdf)

    assert isinstance(parsed, ParsedDocument)
    assert parsed.source_file == "sample_guide.pdf"
    assert "Specimen Transport & Storage" in parsed.title
    assert parsed.total_pages == 3
    assert len(parsed.file_hash) == 64
    assert len(parsed.sections) >= 4

    section_titles = [s.title for s in parsed.sections]
    assert any("Purpose and Scope" in t for t in section_titles)
    assert any("Temperature Categories" in t for t in section_titles)
    assert any("Recollection Policy" in t for t in section_titles)


def test_pdf_parser_page_provenance(sample_pdf: Path):
    """Verify that parsed sections preserve page numbering."""
    parser = PdfParser()
    parsed = parser.parse(sample_pdf)

    purpose_sec = next(s for s in parsed.sections if "Purpose and Scope" in s.title)
    assert purpose_sec.page_start == 2
    assert purpose_sec.page_end == 2
    assert purpose_sec.section_number == "1"

    recollect_sec = next(s for s in parsed.sections if "Recollection Policy" in s.title)
    assert recollect_sec.page_start == 3
    assert recollect_sec.page_end == 3
    assert recollect_sec.section_number == "3"


def test_pdf_parser_nonexistent_file_raises():
    """Verify that a nonexistent file raises controlled PdfParsingError."""
    parser = PdfParser()
    with pytest.raises(PdfParsingError, match="does not exist"):
        parser.parse("nonexistent_path/file.pdf")


def test_pdf_parser_non_pdf_extension_raises(tmp_path: Path):
    """Verify that a non-pdf file raises controlled PdfParsingError."""
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("Plain text content")
    parser = PdfParser()
    with pytest.raises(PdfParsingError, match="not a PDF"):
        parser.parse(txt_file)


def test_pdf_parser_empty_file_raises(tmp_path: Path):
    """Verify that a 0-byte PDF raises controlled PdfParsingError."""
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")
    parser = PdfParser()
    with pytest.raises(PdfParsingError, match="empty"):
        parser.parse(empty_file)


def test_pdf_parser_blank_pages_raises(tmp_path: Path):
    """Verify that a PDF with blank pages (no readable text) raises controlled PdfParsingError."""
    blank_pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()  # Page with no text
    doc.save(str(blank_pdf))
    doc.close()

    parser = PdfParser()
    with pytest.raises(PdfParsingError, match="no readable text"):
        parser.parse(blank_pdf)


def test_pdf_parser_title_override(sample_pdf: Path):
    """Verify that title parameter overrides automatic title detection."""
    parser = PdfParser()
    custom_title = "Authoritative Custom Title"
    parsed = parser.parse(sample_pdf, title=custom_title)
    assert parsed.title == custom_title


def test_pdf_parser_running_header_suppression(sample_pdf: Path):
    """Verify that boilerplate running headers are excluded from extracted content."""
    parser = PdfParser()
    parsed = parser.parse(sample_pdf)
    for section in parsed.sections:
        assert "MediLab AI Assessment - Knowledge Base Document" not in section.content


def test_pdf_parser_malformed_pdf_raises(tmp_path: Path):
    """Verify a corrupt .pdf file fails with a controlled parser error."""
    malformed = tmp_path / "malformed.pdf"
    malformed.write_text("not a valid PDF document", encoding="utf-8")
    parser = PdfParser()
    with pytest.raises(PdfParsingError, match="failed to open PDF"):
        parser.parse(malformed)


def test_pdf_parser_sorts_blocks_by_reading_order(tmp_path: Path):
    """Visual reading order must win over PDF object insertion order."""
    pdf_path = tmp_path / "reading_order.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 220), "2. Second Section\nSecond section body.")
    page.insert_text((50, 100), "1. First Section\nFirst section body.")
    doc.save(str(pdf_path))
    doc.close()

    parsed = PdfParser().parse(pdf_path, title="Reading Order Guide")
    numbered = [section.title for section in parsed.sections if section.section_number]
    assert numbered[:2] == ["1. First Section", "2. Second Section"]
