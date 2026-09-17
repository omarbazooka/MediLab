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
    """Select the best chunks and assemble formatted context with provenance metadata.

    Enforces:
    - Up to max_chunks (default 4).
    - Configurable word budget (default 600 words) and character budget (default 3500 chars).
    - Atomic inclusion: chunks are included as whole, uncut passages (never truncated or fabricated).
    - Deduplicates identical or near-identical text passages.
    - Preserves source attribution: document title, category, version, and chunk indices.
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

        # If adding this chunk would violate the budget, stop adding (unless it's the very first chunk)
        if selected_chunks:
            if max_words is not None and (total_words + chunk_words) > max_words:
                break
            if max_chars is not None and (total_chars + chunk_chars) > max_chars:
                break

        seen_contents.add(normalized)
        selected_chunks.append(chunk)
        total_words += chunk_words
        total_chars += chunk_chars

        if len(selected_chunks) >= max_chunks:
            break

    # Build structured sources list
    sources = [chunk.source_metadata for chunk in selected_chunks]

    # Build cleanly formatted context text
    passages: list[str] = []
    for idx, chunk in enumerate(selected_chunks, start=1):
        header = f"[Source {idx}: {chunk.document_title} ({chunk.document_category}) - v{chunk.document_version} #{chunk.chunk_index}]"
        passages.append(f"{header}\n{chunk.content}")

    formatted_text = "\n\n".join(passages)

    return RetrievalContext(
        chunks=selected_chunks,
        sources=sources,
        formatted_text=formatted_text,
    )
