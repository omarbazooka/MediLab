"""Higher-level application service for KnowledgeDocument CRUD and indexing synchronization."""

from __future__ import annotations

import logging

from app.extensions import db
from app.models.knowledge import KnowledgeDocument
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.indexing import KnowledgeIndexService
from app.repositories.knowledge_repository import KnowledgeRepository

logger = logging.getLogger("medilab.services.knowledge")


class KnowledgeNotFoundError(Exception):
    """Raised when a requested knowledge document is not found."""


class KnowledgeService:
    """Service coordinating knowledge document CRUD and indexing lifecycle."""

    def __init__(
        self,
        repository: KnowledgeRepository | None = None,
        indexer: KnowledgeIndexService | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.repository = repository or KnowledgeRepository()

        if indexer is not None:
            # Respect explicit dependency injection. A caller supplying a ready indexer
            # must not need Jina credentials merely to construct this service.
            self.indexer = indexer
        else:
            provider = embedding_provider or get_embedding_provider()
            self.indexer = KnowledgeIndexService(
                repository=self.repository,
                embedding_provider=provider,
            )

    def get_document(self, document_id: int) -> KnowledgeDocument | None:
        """Fetch a knowledge document by ID."""
        return self.repository.get_document_by_id(document_id)

    def list_documents(
        self,
        category: str | None = None,
        active: bool | None = None,
        index_status: str | None = None,
    ) -> list[KnowledgeDocument]:
        """List knowledge documents matching given filters."""
        return self.repository.list_documents(
            category=category,
            active=active,
            index_status=index_status,
        )

    def create_document(
        self,
        title: str,
        category: str,
        content: str,
        active: bool = True,
        auto_index: bool = True,
    ) -> KnowledgeDocument:
        """Create a new knowledge document and synchronously index it."""
        doc = self.repository.create_document(
            title=title,
            category=category,
            content=content,
            active=active,
            version=1,
            index_status="PENDING",
        )
        db.session.commit()

        if auto_index:
            doc = self.indexer.index_document(doc.id)

        return doc

    def update_document(
        self,
        document_id: int,
        title: str | None = None,
        category: str | None = None,
        content: str | None = None,
        active: bool | None = None,
        auto_index: bool = True,
    ) -> KnowledgeDocument:
        """Update document attributes; if content changes, increment version and reindex."""
        doc = self.repository.get_document_by_id(document_id)
        if doc is None:
            raise KnowledgeNotFoundError(f"KnowledgeDocument {document_id} not found.")

        content_changed = content is not None and content.strip() != doc.content

        if content_changed:
            doc.version += 1
            doc.index_status = "PENDING"

        self.repository.update_document(
            document=doc,
            title=title,
            category=category,
            content=content,
            active=active,
        )
        db.session.commit()

        if content_changed and auto_index:
            doc = self.indexer.index_document(doc.id)

        return doc

    def delete_document(self, document_id: int) -> None:
        """Permanently delete a knowledge document and all its chunks."""
        doc = self.repository.get_document_by_id(document_id)
        if doc is None:
            raise KnowledgeNotFoundError(f"KnowledgeDocument {document_id} not found.")

        self.repository.delete_document(doc)
        db.session.commit()
        logger.info("Deleted knowledge document id=%d and cascaded chunks", document_id)

    def deactivate_document(self, document_id: int) -> KnowledgeDocument:
        """Deactivate a knowledge document, immediately excluding it from retrieval."""
        doc = self.repository.get_document_by_id(document_id)
        if doc is None:
            raise KnowledgeNotFoundError(f"KnowledgeDocument {document_id} not found.")

        doc.active = False
        db.session.commit()
        logger.info("Deactivated knowledge document id=%d", document_id)
        return doc

    def reindex_document(self, document_id: int) -> KnowledgeDocument:
        """Re-index a specific document."""
        return self.indexer.index_document(document_id)

    def reindex_all(self, only_failed: bool = False) -> dict[str, int]:
        """Re-index all active documents across the knowledge base."""
        return self.indexer.reindex_all(only_failed=only_failed)
