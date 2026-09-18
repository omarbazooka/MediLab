"""Deterministic, paragraph-aware text chunker supporting English and Arabic."""

from __future__ import annotations

import re
from typing import Any

# Sentence splitting boundaries for English and Arabic
SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?؟\n])\s+")


def chunk_text(
    content: str,
    max_words: int = 180,
    overlap_words: int = 30,
) -> list[str]:
    """Split text into deterministic passages respecting sentence and paragraph boundaries.

    If total word count is <= max_words, the text is returned as a single chunk without splitting.
    """
    clean_content = content.strip()
    if not clean_content:
        return []

    words = clean_content.split()
    total_words = len(words)

    # Return small texts intact
    if total_words <= max_words:
        return [clean_content]

    # Split into structural paragraphs first
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", clean_content) if p.strip()]
    if not paragraphs:
        paragraphs = [clean_content]

    # Break paragraphs into atomic sentence segments
    segments: list[str] = []
    for para in paragraphs:
        sentences = [s.strip() for s in SENTENCE_SPLIT_REGEX.split(para) if s.strip()]
        if sentences:
            segments.extend(sentences)
        else:
            segments.append(para)

    chunks: list[str] = []
    current_words: list[str] = []

    for seg in segments:
        seg_words = seg.split()
        if not seg_words:
            continue

        # If a single sentence exceeds max_words, window it directly
        if len(seg_words) > max_words:
            # Flush accumulated words first
            if current_words:
                chunks.append(" ".join(current_words))
                current_words = []

            step = max(1, max_words - overlap_words)
            for i in range(0, len(seg_words), step):
                chunk_slice = seg_words[i : i + max_words]
                if chunk_slice:
                    chunks.append(" ".join(chunk_slice))
            continue

        # Check if adding this segment exceeds max_words
        if len(current_words) + len(seg_words) > max_words:
            chunks.append(" ".join(current_words))
            # Start next chunk with overlap from the tail of current_words
            overlap = current_words[-overlap_words:] if overlap_words > 0 else []
            current_words = overlap + seg_words
        else:
            current_words.extend(seg_words)

    if current_words:
        chunks.append(" ".join(current_words))

    # Deduplicate exact adjacent chunks if overlap produced identical slices
    unique_chunks: list[str] = []
    for c in chunks:
        c_stripped = c.strip()
        if c_stripped and (not unique_chunks or unique_chunks[-1] != c_stripped):
            unique_chunks.append(c_stripped)

    return unique_chunks


def chunk_document(
    content: str,
    document_id: int,
    document_version: int,
    title: str,
    category: str,
    max_words: int = 180,
    overlap_words: int = 30,
) -> list[dict[str, Any]]:
    """Produce structured chunk specifications with metadata for database persistence."""
    text_chunks = chunk_text(content, max_words=max_words, overlap_words=overlap_words)
    result: list[dict[str, Any]] = []

    for idx, text in enumerate(text_chunks):
        word_count = len(text.split())
        result.append(
            {
                "chunk_index": idx,
                "content": text,
                "metadata": {
                    "document_id": document_id,
                    "document_version": document_version,
                    "title": title,
                    "category": category,
                    "chunk_index": idx,
                    "word_count": word_count,
                },
            }
        )

    return result


# Configurable engineering defaults for structure-aware PDF chunking
PDF_CHUNK_SIZE: int = 1400  # Target character size per chunk
PDF_CHUNK_OVERLAP: int = 200  # Character overlap for oversized section splits


def chunk_parsed_document(
    parsed_doc: Any,
    document_id: int,
    document_version: int,
    category: str,
    chunk_size: int = PDF_CHUNK_SIZE,
    chunk_overlap: int = PDF_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """Produce structure-aware chunk specifications from a ParsedDocument.

    Preserves section boundaries so unrelated headings are never mixed across chunks.
    Oversized sections are recursively split using RecursiveCharacterTextSplitter.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "؟ ", "! ", " ", ""],
    )

    result: list[dict[str, Any]] = []
    chunk_idx = 0

    for section in parsed_doc.sections:
        clean_text = section.content.strip()
        if not clean_text:
            continue

        # If section fits within chunk_size, keep as a single atomic chunk
        if len(clean_text) <= chunk_size:
            text_pieces = [clean_text]
        else:
            # Oversized section: split recursively inside this section only
            text_pieces = splitter.split_text(clean_text)

        for piece in text_pieces:
            piece_clean = piece.strip()
            if not piece_clean:
                continue

            result.append(
                {
                    "chunk_index": chunk_idx,
                    "content": piece_clean,
                    "metadata": {
                        "document_id": document_id,
                        "document_version": document_version,
                        "title": parsed_doc.title,
                        "category": category,
                        "source_file": parsed_doc.source_file,
                        "source_type": "pdf",
                        "section_title": section.title,
                        "section_number": section.section_number,
                        "page_start": section.page_start,
                        "page_end": section.page_end,
                        "chunk_index": chunk_idx,
                        "content_hash": parsed_doc.file_hash,
                        "char_count": len(piece_clean),
                        "word_count": len(piece_clean.split()),
                    },
                }
            )
            chunk_idx += 1

    return result
