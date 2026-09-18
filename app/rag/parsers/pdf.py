"""Structure-aware PDF document parser using PyMuPDF."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz
except ImportError:
    import fitz

logger = logging.getLogger("medilab.rag.parsers.pdf")

# Running header pattern across assessment documents
RUNNING_HEADER_REGEX = re.compile(
    r"^MediLab AI Assessment - Knowledge Base Document - Version \d+\.\d+$",
    re.IGNORECASE,
)

# Numbered section heading pattern: e.g. "1. Purpose and Scope", "3. Fasting and Hydration"
NUMBERED_HEADING_REGEX = re.compile(
    r"^(\d{1,2}(?:\.\d{1,2})*)\.?\s+([A-Z0-9\u0600-\u06FF][^\n]{2,100})$"
)

# Named unnumbered structural section headings
KNOWN_STRUCTURAL_HEADINGS = {
    "quick reference",
    "document control notes",
    "overview",
    "executive summary",
}


class PdfParsingError(Exception):
    """Raised when PDF validation or extraction fails."""


@dataclass(frozen=True)
class ParsedBlock:
    """Atomic text block extracted from a PDF page."""

    text: str
    page_number: int  # 1-indexed
    bbox: tuple[float, float, float, float]
    block_number: int
    block_type: int = 0


@dataclass
class ParsedSection:
    """Logical document section delimited by structural headings."""

    title: str
    section_number: str | None
    content: str
    page_start: int
    page_end: int
    blocks: list[ParsedBlock] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.content.split())

    @property
    def char_count(self) -> int:
        return len(self.content)


@dataclass
class ParsedDocument:
    """Fully extracted and structured representation of a PDF document."""

    source_file: str
    title: str
    total_pages: int
    sections: list[ParsedSection]
    raw_text: str
    file_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PdfParser:
    """Extracts structured sections, text blocks, and page provenance from PDF files."""

    def __init__(self, max_file_size_bytes: int = 50 * 1024 * 1024) -> None:
        self.max_file_size_bytes = max_file_size_bytes

    def validate_file(self, file_path: str | Path) -> Path:
        """Validate that the file exists, is a PDF, and is within size constraints."""
        path = Path(file_path).resolve()
        if not path.exists():
            raise PdfParsingError(f"PDF file does not exist: '{path}'")
        if not path.is_file():
            raise PdfParsingError(f"Path is not a regular file: '{path}'")
        if path.suffix.lower() != ".pdf":
            raise PdfParsingError(f"File '{path.name}' is not a PDF (extension is {path.suffix})")

        file_size = path.stat().st_size
        if file_size == 0:
            raise PdfParsingError(f"PDF file '{path.name}' is empty (0 bytes)")
        if file_size > self.max_file_size_bytes:
            raise PdfParsingError(
                f"PDF file '{path.name}' exceeds maximum allowed size "
                f"({file_size} > {self.max_file_size_bytes} bytes)"
            )

        return path

    @staticmethod
    def compute_sha256(path: Path) -> str:
        """Compute the SHA-256 hash of a file for change detection and audit."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def parse(
        self,
        file_path: str | Path,
        title: str | None = None,
    ) -> ParsedDocument:
        """Parse a PDF file into a structure-aware ParsedDocument."""
        path = self.validate_file(file_path)
        file_hash = self.compute_sha256(path)

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            raise PdfParsingError(f"PyMuPDF failed to open PDF '{path.name}': {exc}") from exc

        try:
            total_pages = len(doc)
            if total_pages == 0:
                raise PdfParsingError(f"PDF '{path.name}' has 0 pages.")

            # Collect raw text and blocks page by page
            all_blocks: list[ParsedBlock] = []
            page_texts: list[str] = []

            for page_idx in range(total_pages):
                page = doc[page_idx]
                page_num = page_idx + 1
                raw_blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, type)

                page_str = page.get_text().strip()
                if page_str:
                    page_texts.append(page_str)

                for b in raw_blocks:
                    text = b[4].strip()
                    if not text:
                        continue
                    # Filter out running header boilerplate
                    if RUNNING_HEADER_REGEX.match(text):
                        continue

                    block = ParsedBlock(
                        text=text,
                        page_number=page_num,
                        bbox=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                        block_number=int(b[5]),
                        block_type=int(b[6]),
                    )
                    all_blocks.append(block)

            raw_combined = "\n\n".join(page_texts).strip()
            if not raw_combined:
                raise PdfParsingError(
                    f"PDF '{path.name}' contains no readable text content (possibly scanned/image-only)."
                )

            # Detect document title and structure sections
            doc_title = (
                title.strip() if title else self._detect_document_title(doc, all_blocks, path.stem)
            )
            sections = self._extract_sections(all_blocks, doc_title)

            return ParsedDocument(
                source_file=path.name,
                title=doc_title,
                total_pages=total_pages,
                sections=sections,
                raw_text=raw_combined,
                file_hash=file_hash,
                metadata={
                    "page_count": total_pages,
                    "section_count": len(sections),
                    "file_size": path.stat().st_size,
                },
            )
        finally:
            doc.close()

    def _detect_document_title(
        self,
        doc: Any,
        blocks: list[ParsedBlock],
        fallback_stem: str,
    ) -> str:
        """Extract or infer the authoritative document title from PDF content."""
        page1_blocks = [b for b in blocks if b.page_number == 1]

        # 1. Structural pattern in MediLab docs: title blocks between "MEDILAB" and "Knowledge Base Category"
        medilab_idx: int | None = None
        category_idx: int | None = None
        for idx, b in enumerate(page1_blocks):
            txt = b.text.strip()
            if txt.upper() == "MEDILAB":
                medilab_idx = idx
            elif "knowledge base category" in txt.lower() and category_idx is None:
                category_idx = idx

        if medilab_idx is not None and category_idx is not None and category_idx > medilab_idx + 1:
            title_parts = [
                b.text.strip()
                for b in page1_blocks[medilab_idx + 1 : category_idx]
                if b.text.strip()
            ]
            if title_parts:
                return " ".join(title_parts)

        # 2. Check page 1 blocks for prominent title blocks
        for idx, b in enumerate(page1_blocks):
            lines = [line.strip() for line in b.text.splitlines() if line.strip()]
            for line in lines:
                if line.upper() == "MEDILAB":
                    continue
                if any(
                    kw in line.lower()
                    for kw in ("guide", "policy", "preparation", "turnaround", "collection")
                ):
                    if idx + 1 < len(page1_blocks):
                        next_b = page1_blocks[idx + 1]
                        next_line = next_b.text.strip()
                        if next_line.lower() in ("guide", "policy"):
                            return f"{line} {next_line}"
                    return line

        # 3. Check document metadata
        meta_title = (doc.metadata or {}).get("title")
        if meta_title and len(meta_title.strip()) > 3:
            return meta_title.strip()

        # 4. Fallback to humanized stem
        clean_stem = re.sub(r"^\d+_", "", fallback_stem).replace("_", " ").strip()
        return clean_stem

    def _extract_sections(
        self,
        blocks: list[ParsedBlock],
        doc_title: str,
    ) -> list[ParsedSection]:
        """Segment block stream into logical sections by identifying section headers."""
        sections: list[ParsedSection] = []
        current_title = "Overview"
        current_num: str | None = None
        current_blocks: list[ParsedBlock] = []

        def flush_current():
            nonlocal current_title, current_num, current_blocks
            if not current_blocks:
                return

            text_parts = []
            for b in current_blocks:
                text = b.text.strip()
                if not text:
                    continue
                text_parts.append(text)

            content = "\n\n".join(text_parts).strip()
            if content:
                p_start = min(b.page_number for b in current_blocks)
                p_end = max(b.page_number for b in current_blocks)
                sections.append(
                    ParsedSection(
                        title=current_title,
                        section_number=current_num,
                        content=content,
                        page_start=p_start,
                        page_end=p_end,
                        blocks=list(current_blocks),
                    )
                )
            current_blocks = []

        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            first_line = text.splitlines()[0].strip()

            # Check if block starts with a numbered heading
            num_match = NUMBERED_HEADING_REGEX.match(first_line)
            is_structural = first_line.lower() in KNOWN_STRUCTURAL_HEADINGS

            if num_match:
                flush_current()
                current_num = num_match.group(1)
                heading_text = num_match.group(2).strip()
                current_title = f"{current_num}. {heading_text}"

                # If block has body content following the heading line, include it in section
                remaining_lines = text.splitlines()[1:]
                body_text = "\n".join(remaining_lines).strip()
                if body_text:
                    sub_block = ParsedBlock(
                        text=body_text,
                        page_number=block.page_number,
                        bbox=block.bbox,
                        block_number=block.block_number,
                        block_type=block.block_type,
                    )
                    current_blocks.append(sub_block)
                continue

            elif is_structural:
                flush_current()
                current_num = None
                current_title = first_line

                remaining_lines = text.splitlines()[1:]
                body_text = "\n".join(remaining_lines).strip()
                if body_text:
                    sub_block = ParsedBlock(
                        text=body_text,
                        page_number=block.page_number,
                        bbox=block.bbox,
                        block_number=block.block_number,
                        block_type=block.block_type,
                    )
                    current_blocks.append(sub_block)
                continue

            # Otherwise, append block to active section
            current_blocks.append(block)

        flush_current()

        # If no sections were identified, wrap all blocks as a single section
        if not sections and blocks:
            content = "\n\n".join(b.text.strip() for b in blocks if b.text.strip())
            p_start = min(b.page_number for b in blocks)
            p_end = max(b.page_number for b in blocks)
            sections.append(
                ParsedSection(
                    title=doc_title,
                    section_number=None,
                    content=content,
                    page_start=p_start,
                    page_end=p_end,
                    blocks=list(blocks),
                )
            )

        return sections
