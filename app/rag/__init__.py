"""MediLab AI RAG Core package."""

from typing import Any

from app.rag.embeddings import (
    DeterministicFakeEmbeddingProvider,
    EmbeddingConfigError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingProviderError,
    JinaEmbeddingProvider,
)
from app.rag.types import (
    RAGResult,
    RetrievalContext,
    RetrievalDiagnostics,
    RetrievalFilters,
    RetrievalOutcome,
    RetrievedChunk,
    RewriteResult,
)


def __getattr__(name: str) -> Any:
    if name in {"KnowledgeIndexService", "KnowledgeIndexingError"}:
        from app.rag.indexing import KnowledgeIndexingError, KnowledgeIndexService

        return KnowledgeIndexService if name == "KnowledgeIndexService" else KnowledgeIndexingError
    if name in {"RAGService", "RAGRetrievalError"}:
        from app.rag.service import RAGRetrievalError, RAGService

        return RAGService if name == "RAGService" else RAGRetrievalError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DeterministicFakeEmbeddingProvider",
    "EmbeddingConfigError",
    "EmbeddingError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "JinaEmbeddingProvider",
    "KnowledgeIndexService",
    "KnowledgeIndexingError",
    "RAGResult",
    "RAGRetrievalError",
    "RAGService",
    "RetrievalContext",
    "RetrievalDiagnostics",
    "RetrievalFilters",
    "RetrievalOutcome",
    "RetrievedChunk",
    "RewriteResult",
]
