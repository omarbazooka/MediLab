"""Unit tests for KnowledgeService and KnowledgeIndexService lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.extensions import db
from app.rag.embeddings import DeterministicFakeEmbeddingProvider
from app.rag.indexing import KnowledgeIndexingError, KnowledgeIndexService
from app.services.knowledge_service import KnowledgeService


def test_knowledge_service_create_document(app) -> None:
    with app.app_context():
        db.create_all()
        service = KnowledgeService(
            embedding_provider=DeterministicFakeEmbeddingProvider(),
        )

        doc = service.create_document(
            title="Sample Guideline",
            category="Preparation",
            content="Fast for 8 hours before test.",
            active=True,
        )

        assert doc.id is not None
        assert doc.index_status == "READY"
        assert doc.version == 1
        assert doc.last_indexed_at is not None

        chunks = service.repository.get_chunks_by_document(doc.id)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].content == "Fast for 8 hours before test."
        assert len(chunks[0].embedding) == 384


def test_knowledge_service_update_content_increments_version_and_reindexes(app) -> None:
    with app.app_context():
        db.create_all()
        service = KnowledgeService(
            embedding_provider=DeterministicFakeEmbeddingProvider(),
        )

        doc = service.create_document(
            title="Original Title",
            category="Policies",
            content="Original content version 1.",
        )
        assert doc.version == 1

        updated = service.update_document(
            document_id=doc.id,
            content="Updated content version 2 with more information.",
        )
        assert updated.version == 2
        assert updated.index_status == "READY"

        chunks = service.repository.get_chunks_by_document(doc.id)
        assert len(chunks) == 1
        assert chunks[0].content == "Updated content version 2 with more information."
        assert chunks[0].metadata_["document_version"] == 2


def test_knowledge_service_delete_cascades_chunks(app) -> None:
    with app.app_context():
        db.create_all()
        service = KnowledgeService(
            embedding_provider=DeterministicFakeEmbeddingProvider(),
        )

        doc = service.create_document(
            title="Doc To Delete",
            category="FAQ",
            content="Content to be deleted.",
        )
        doc_id = doc.id
        assert len(service.repository.get_chunks_by_document(doc_id)) == 1

        service.delete_document(doc_id)
        assert service.get_document(doc_id) is None
        assert len(service.repository.get_chunks_by_document(doc_id)) == 0


def test_knowledge_service_deactivate_sets_inactive(app) -> None:
    with app.app_context():
        db.create_all()
        service = KnowledgeService(
            embedding_provider=DeterministicFakeEmbeddingProvider(),
        )

        doc = service.create_document(
            title="Doc To Deactivate",
            category="FAQ",
            content="Content to be deactivated.",
        )
        deactivated = service.deactivate_document(doc.id)
        assert deactivated.active is False


def test_knowledge_service_respects_injected_indexer_without_provider_factory(
    app, monkeypatch
) -> None:
    """Supplying an indexer must not require Jina configuration during construction."""
    with app.app_context():
        db.create_all()
        custom_indexer = MagicMock(spec=KnowledgeIndexService)

        def fail_if_called():
            raise AssertionError("get_embedding_provider must not run for an injected indexer")

        monkeypatch.setattr(
            "app.services.knowledge_service.get_embedding_provider",
            fail_if_called,
        )

        service = KnowledgeService(indexer=custom_indexer)
        assert service.indexer is custom_indexer


def test_knowledge_index_service_failure_sets_failed_status_and_safe_error(app) -> None:
    with app.app_context():
        db.create_all()

        failing_provider = MagicMock()
        failing_provider.embed_documents.side_effect = RuntimeError(
            "Bearer super-secret-key-123 failed: connection timeout"
        )

        indexer = KnowledgeIndexService(embedding_provider=failing_provider)
        service = KnowledgeService(indexer=indexer)

        # Create document without auto_index to simulate step-by-step
        doc = service.create_document(
            title="Failing Doc",
            category="Preparation",
            content="Content will fail embedding.",
            auto_index=False,
        )
        assert doc.index_status == "PENDING"

        with pytest.raises(KnowledgeIndexingError):
            service.reindex_document(doc.id)

        failed_doc = service.get_document(doc.id)
        assert failed_doc.index_status == "FAILED"
        assert failed_doc.index_error is not None
        # Verify secret masking
        assert "super-secret-key-123" not in failed_doc.index_error
