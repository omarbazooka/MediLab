"""Final retrieval context assembly and source metadata formatting."""

from __future__ import annotations

from app.rag.types import RetrievalContext, RetrievedChunk

DEFAULT_MAX_CONTEXT_CHUNKS = 4
DEFAULT_MAX_CONTEXT_WORDS = 600
DEFAULT_MAX_CONTEXT_CHARS = 3500


def build_retrieval_context(
    fused_chunks: list[RetrievedChunk],
    max_chunks: int = DEFAULT_MAX_CONTEXT_CHUNKS,
    max_words: int | None = DEFAULT_MAX_CONTEXT_WORDS,
    max_chars: int | None = DEFAULT_MAX_CONTEXT_CHARS,
) -> RetrievalContext:
    """Select the best whole chunks within deterministic context budgets.

    Enforces:
    - Up to max_chunks (default 4).
    - Configurable word budget (default 600 words) and character budget (default 3500 chars).
    - Atomic inclusion: chunks are included whole or skipped; text is never sliced/fabricated.
    - Deduplication of identical normalized passages.
    - Source attribution: document title, category, version, and chunk index.
    """
    if not fused_chunks:
        return RetrievalContext()

    selected_chunks: list[RetrievedChunk] = []
    seen_contents: set[str] = set()
    total_words = 0
    total_chars = 0

    for chunk in fused_chunks:
        normalized = " ".join(chunk.content.split()).lower()
        if normalized in seen_contents:
            continue

        chunk_words = len(chunk.content.split())
        chunk_chars = len(chunk.content)

        if max_words is not None and (total_words + chunk_words) > max_words:
            continue
        if max_chars is not None and (total_chars + chunk_chars) > max_chars:
            continue

        seen_contents.add(normalized)
        selected_chunks.append(chunk)
        total_words += chunk_words
        total_chars += chunk_chars

        if len(selected_chunks) >= max_chunks:
            break

    sources = [chunk.source_metadata for chunk in selected_chunks]

    passages: list[str] = []
    for idx, chunk in enumerate(selected_chunks, start=1):
        provenance_parts = [f"{chunk.document_title} ({chunk.document_category})"]
        if chunk.section_title:
            provenance_parts.append(f"Section: {chunk.section_title}")
        if chunk.page_start:
            if chunk.page_end and chunk.page_end != chunk.page_start:
                provenance_parts.append(f"pp. {chunk.page_start}-{chunk.page_end}")
            else:
                provenance_parts.append(f"p. {chunk.page_start}")
        provenance_parts.append(f"v{chunk.document_version} #{chunk.chunk_index}")

        header = f"[Source {idx}: {' | '.join(provenance_parts)}]"
        passages.append(f"{header}\n{chunk.content}")

    return RetrievalContext(
        chunks=selected_chunks,
        sources=sources,
        formatted_text="\n\n".join(passages),
    )
