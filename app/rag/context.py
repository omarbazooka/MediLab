"""Final retrieval context assembly and source metadata formatting."""

from __future__ import annotations

from app.rag.types import RetrievalContext, RetrievedChunk

DEFAULT_MAX_CONTEXT_CHUNKS = 4


def build_retrieval_context(
    fused_chunks: list[RetrievedChunk],
    max_chunks: int = DEFAULT_MAX_CONTEXT_CHUNKS,
) -> RetrievalContext:
    """Select the best chunks and assemble formatted context with provenance metadata.

    - Retains up to max_chunks (default 4).
    - Deduplicates identical or near-identical text passages.
    - Preserves source attribution: document title, category, version, and chunk indices.
    """
    if not fused_chunks:
        return RetrievalContext()

    selected_chunks: list[RetrievedChunk] = []
    seen_contents: set[str] = set()

    for chunk in fused_chunks:
        normalized = " ".join(chunk.content.split()).lower()
        if normalized in seen_contents:
            continue
        seen_contents.add(normalized)
        selected_chunks.append(chunk)

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
