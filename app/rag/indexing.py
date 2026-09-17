"""Knowledge indexing service managing document lifecycle and chunk synchronization."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from app.extensions import db
from app.models.knowledge import KnowledgeDocument
from app.rag.chunking import chunk_document
from app.rag.embeddings import EmbeddingProvider, JinaEmbeddingProvider
from app.repositories.knowledge_repository import KnowledgeRepository

logger = logging.getLogger("medilab.rag.indexing")


class KnowledgeIndexingError(Exception):
    """Raised when knowledge document indexing fails."""


class KnowledgeIndexService:
    """Orchestrates chunking, embedding generation, and atomic chunk persistence for documents."""

    def __init__(
        self,
        repository: KnowledgeRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.repository = repository or KnowledgeRepository()
        self.embedding_provider = embedding_provider or JinaEmbeddingProvider()

    def index_document(self, document_id: int) -> KnowledgeDocument:
        """Index or re-index a single document.

        Lifecycle:
        1. Mark INDEXING.
        2. Chunk text content.
        3. Embed all chunks with passage task (retrieval.passage @ 384 dim).
        4. Transactionally replace old chunks with new chunks.
        5. Mark READY and update last_indexed_at.
        6. On failure: rollback chunk mutation, mark FAILED with safe error message.
        """
        doc = self.repository.get_document_by_id(document_id)
        if doc is None:
            raise KnowledgeIndexingError(f"KnowledgeDocument {document_id} not found.")

        # 1. Transition to INDEXING
        self.repository.set_document_status(doc.id, "INDEXING")
        db.session.commit()

        try:
            # 2. Deterministic chunking
            chunk_specs = chunk_document(
                content=doc.content,
                document_id=doc.id,
                document_version=doc.version,
                title=doc.title,
                category=doc.category,
            )

            texts = [spec["content"] for spec in chunk_specs]

            # 3. Generate 384-dimensional passage embeddings
            embeddings = self.embedding_provider.embed_documents(texts) if texts else []

            # 4. Atomic chunk replacement inside transaction
            self.repository.replace_document_chunks(
                document_id=doc.id,
                chunk_specs=chunk_specs,
                embeddings=embeddings,
            )

            # 5. Transition to READY
            self.repository.set_document_status(
                document_id=doc.id,
                status="READY",
                error=None,
                indexed_at=datetime.now(UTC),
            )
            db.session.commit()
            logger.info(
                "Successfully indexed document id=%d with %d chunks", doc.id, len(chunk_specs)
            )
            return doc

        except Exception as exc:
            db.session.rollback()
            # Sanitize error message to prevent leaking secrets, credentials, or internal paths
            raw_err = str(exc)
            safe_err = re.sub(r"(Bearer\s+)[a-zA-Z0-9_\-]+", r"\1[REDACTED]", raw_err, flags=re.I)
            safe_err = re.sub(
                r"postgresql(?:\+psycopg)?://[^@]+@", "postgresql://[REDACTED]@", safe_err
            )
            safe_err = safe_err[:400]

            logger.error("Failed indexing document id=%d: %s", doc.id, safe_err)
            self.repository.set_document_status(
                document_id=doc.id,
                status="FAILED",
                error=safe_err,
            )
            db.session.commit()
            raise KnowledgeIndexingError(f"Indexing document {doc.id} failed: {safe_err}") from exc

    def reindex_all(self, only_failed: bool = False) -> dict[str, int]:
        """Re-index all active documents, or only previously failed documents.

        Returns:
            dict with counts: {'total': N, 'indexed': M, 'failed': K}
        """
        status_filter = "FAILED" if only_failed else None
        docs = self.repository.list_documents(active=True, index_status=status_filter)

        counts = {"total": len(docs), "indexed": 0, "failed": 0}
        for doc in docs:
            try:
                self.index_document(doc.id)
                counts["indexed"] += 1
            except Exception:
                counts["failed"] += 1

        return counts
