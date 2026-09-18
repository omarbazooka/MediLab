"""Data types, dataclasses, and data contracts for MediLab AI RAG Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RetrievalOutcome(StrEnum):
    """Authoritative retrieval grading outcomes."""

    GOOD = "GOOD"
    WEAK_RETRY = "WEAK_RETRY"
    AMBIGUOUS_USER_QUERY = "AMBIGUOUS_USER_QUERY"
    NO_KNOWLEDGE = "NO_KNOWLEDGE"


@dataclass(frozen=True)
class RetrievalFilters:
    """Explicit, typed metadata filters for retrieval candidates."""

    category: str | None = None
    document_ids: list[int] | None = None


@dataclass(frozen=True)
class SemanticCandidate:
    """Candidate chunk returned by pgvector cosine distance search."""

    chunk_id: int
    document_id: int
    document_title: str
    document_category: str
    document_version: int
    chunk_index: int
    content: str
    cosine_distance: float
    semantic_rank: int
    chunk_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LexicalCandidate:
    """Candidate chunk returned by PostgreSQL Full-Text Search."""

    chunk_id: int
    document_id: int
    document_title: str
    document_category: str
    document_version: int
    chunk_index: int
    content: str
    fts_score: float
    lexical_rank: int
    chunk_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    """Fused chunk representation retaining dual-arm ranks, scores, and metadata."""

    chunk_id: int
    document_id: int
    document_title: str
    document_category: str
    document_version: int
    chunk_index: int
    content: str
    semantic_rank: int | None = None
    lexical_rank: int | None = None
    cosine_distance: float | None = None
    fts_score: float | None = None
    rrf_score: float = 0.0
    chunk_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def section_title(self) -> str | None:
        return self.chunk_metadata.get("section_title")

    @property
    def page_start(self) -> int | None:
        return self.chunk_metadata.get("page_start")

    @property
    def page_end(self) -> int | None:
        return self.chunk_metadata.get("page_end")

    @property
    def source_file(self) -> str | None:
        return self.chunk_metadata.get("source_file")

    @property
    def source_metadata(self) -> dict[str, Any]:
        """Structured source provenance for client inspection and audit."""
        base: dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "title": self.document_title,
            "category": self.document_category,
            "version": self.document_version,
            "chunk_index": self.chunk_index,
            "semantic_rank": self.semantic_rank,
            "lexical_rank": self.lexical_rank,
            "rrf_score": round(self.rrf_score, 6),
        }
        if self.chunk_metadata:
            for k in (
                "source_file",
                "source_type",
                "section_title",
                "section_number",
                "page_start",
                "page_end",
                "content_hash",
            ):
                if k in self.chunk_metadata:
                    base[k] = self.chunk_metadata[k]
        return base


@dataclass(frozen=True)
class RewriteResult:
    """Outcome of context-aware query rewrite evaluation."""

    original_query: str
    rewritten_query: str
    is_ambiguous: bool = False
    resolved_entity: str | None = None
    status: str = "NORMAL"  # "NORMAL", "REWRITTEN", "AMBIGUOUS_USER_QUERY"


@dataclass
class RetrievalDiagnostics:
    """Observability metrics and execution timings across retrieval stages."""

    rewrite_ms: float = 0.0
    embed_ms: float = 0.0
    semantic_ms: float = 0.0
    lexical_ms: float = 0.0
    fusion_ms: float = 0.0
    grading_ms: float = 0.0
    context_ms: float = 0.0
    total_ms: float = 0.0
    attempt_count: int = 1
    semantic_candidates_count: int = 0
    lexical_candidates_count: int = 0
    degraded_mode: bool = False
    degraded_reason: str | None = None
    retry_used: bool = False


@dataclass
class RetrievalContext:
    """Final assembled context containing top passages and structured source references."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    formatted_text: str = ""


@dataclass
class RAGResult:
    """Final result of the standalone RAG retrieval pipeline."""

    original_query: str
    rewritten_query: str
    outcome: str
    attempt_count: int
    final_chunks: list[RetrievedChunk] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    context: RetrievalContext | None = None
    diagnostics: RetrievalDiagnostics = field(default_factory=RetrievalDiagnostics)
    degraded_mode: bool = False
    latency_ms: float = 0.0
