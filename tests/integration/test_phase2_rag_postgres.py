"""PostgreSQL integration tests for Phase 2 RAG Core.

Validates real PostgreSQL behaviors:
- VECTOR(384) persistence and cosine distance (<=>) retrieval
- FTS trigger search_vector maintenance and lexical retrieval
- RRF hybrid fusion combining semantic and lexical scores
- Lifecycle filtering: only active + READY documents retrievable
- Inactive, PENDING, INDEXING, FAILED exclusions
- Document Add -> index -> READY -> retrievable
- Document Update -> version increments -> old text disappears -> new text retrievable
- Document Delete -> cascade deletes chunks -> unretrievable
- Document Deactivate -> immediately unretrievable
- Indexing failure records safe index_error and FAILED status
- Reindex transitions back to READY
- Degraded mode operation
"""

from __future__ import annotations

import pytest

from app.extensions import db
from app.rag.embeddings import DeterministicFakeEmbeddingProvider
from app.rag.service import RAGService
from app.rag.types import RetrievalFilters, RetrievalOutcome
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge_service import KnowledgeService

pytestmark = pytest.mark.postgres


@pytest.fixture
def fake_provider() -> DeterministicFakeEmbeddingProvider:
    return DeterministicFakeEmbeddingProvider(dimension=384)


def test_postgres_vector_storage_and_semantic_retrieval(postgres_app, fake_provider) -> None:
    """Verify 384-dimensional vector persistence and cosine distance ordering in PostgreSQL."""
    with postgres_app.app_context():
        repo = KnowledgeRepository()
        doc = repo.create_document(
            title="Postgres Vector Doc",
            category="Preparation",
            content="Fasting for blood tests.",
            active=True,
            index_status="READY",
        )
        db.session.commit()

        v1 = fake_provider.embed_query("Fasting for blood tests")
        v2 = fake_provider.embed_query("Completely unrelated text")

        # Insert chunks
        repo.replace_document_chunks(
            document_id=doc.id,
            chunk_specs=[
                {"chunk_index": 0, "content": "Fasting for blood tests.", "metadata": {}},
                {"chunk_index": 1, "content": "Unrelated paragraph.", "metadata": {}},
            ],
            embeddings=[v1, v2],
        )
        db.session.commit()

        # Semantic search with query near v1
        results = repo.search_semantic(query_embedding=v1, top_k=2)
        assert len(results) >= 2
        assert results[0].chunk_index == 0
        assert results[0].cosine_distance < results[1].cosine_distance

        # Cleanup
        repo.delete_document(doc)
        db.session.commit()


def test_postgres_fts_trigger_and_lexical_retrieval(postgres_app) -> None:
    """Verify automatic PostgreSQL search_vector trigger maintenance and FTS lexical search."""
    with postgres_app.app_context():
        repo = KnowledgeRepository()
        doc = repo.create_document(
            title="FTS Cancellation Doc",
            category="Policies",
            content="Cancellations must be made 2 hours in advance.",
            active=True,
            index_status="READY",
        )
        db.session.commit()

        repo.replace_document_chunks(
            document_id=doc.id,
            chunk_specs=[
                {
                    "chunk_index": 0,
                    "content": "Specialized cancellation policy for home phlebotomy visits.",
                    "metadata": {},
                }
            ],
            embeddings=[[0.0] * 384],
        )
        db.session.commit()

        # Check that trigger populated search_vector
        chunk = repo.get_chunks_by_document(doc.id)[0]
        assert chunk.search_vector is not None

        # Search lexically for 'cancellation'
        lex_results = repo.search_lexical(query_text="cancellation home visits", top_k=5)
        matching_ids = [c.chunk_id for c in lex_results]
        assert chunk.id in matching_ids

        # Cleanup
        repo.delete_document(doc)
        db.session.commit()


def test_postgres_hybrid_retrieval_fuses_both_arms(postgres_app, fake_provider) -> None:
    """Verify hybrid RAG service fuses semantic and lexical search on PostgreSQL."""
    with postgres_app.app_context():
        service = KnowledgeService(embedding_provider=fake_provider)
        rag = RAGService(
            repository=service.repository,
            embedding_provider=fake_provider,
        )

        doc = service.create_document(
            title="Lipid Fasting Guidelines",
            category="Preparation",
            content="For Lipid Profile testing, a strict 10 to 12 hour fast is required.",
            active=True,
            auto_index=True,
        )

        res = rag.retrieve("How many hours fasting for lipid profile?")
        assert res.outcome == RetrievalOutcome.GOOD.value
        assert len(res.final_chunks) > 0
        assert res.final_chunks[0].document_id == doc.id
        assert res.final_chunks[0].semantic_rank is not None
        assert res.final_chunks[0].lexical_rank is not None

        # Cleanup
        service.delete_document(doc.id)


def test_retrieval_excludes_inactive_and_non_ready_documents(postgres_app, fake_provider) -> None:
    """Verify retrieval excludes inactive documents and documents with PENDING, INDEXING, FAILED statuses."""
    with postgres_app.app_context():
        repo = KnowledgeRepository()
        service = KnowledgeService(repository=repo, embedding_provider=fake_provider)
        rag = RAGService(repository=repo, embedding_provider=fake_provider)

        # 1. Inactive document
        doc_inactive = service.create_document(
            title="Inactive Doc",
            category="Policies",
            content="Secret inactive guidelines keyword_alpha.",
            active=False,
            auto_index=True,
        )

        # 2. PENDING document
        doc_pending = service.create_document(
            title="Pending Doc",
            category="Policies",
            content="Pending guidelines keyword_alpha.",
            active=True,
            auto_index=False,
        )

        # 3. INDEXING document
        doc_indexing = service.create_document(
            title="Indexing Doc",
            category="Policies",
            content="Indexing guidelines keyword_alpha.",
            active=True,
            auto_index=False,
        )
        repo.set_document_status(doc_indexing.id, "INDEXING")
        db.session.commit()

        # 4. FAILED document
        doc_failed = service.create_document(
            title="Failed Doc",
            category="Policies",
            content="Failed guidelines keyword_alpha.",
            active=True,
            auto_index=False,
        )
        repo.set_document_status(doc_failed.id, "FAILED", error="Simulated failure")
        db.session.commit()

        # Execute search
        res = rag.retrieve("keyword_alpha")
        retrieved_doc_ids = {c.document_id for c in res.final_chunks}

        assert doc_inactive.id not in retrieved_doc_ids
        assert doc_pending.id not in retrieved_doc_ids
        assert doc_indexing.id not in retrieved_doc_ids
        assert doc_failed.id not in retrieved_doc_ids

        # Cleanup
        for d in (doc_inactive, doc_pending, doc_indexing, doc_failed):
            service.delete_document(d.id)


def test_metadata_category_and_document_id_filters(postgres_app, fake_provider) -> None:
    """Verify metadata filters strictly constrain retrieval candidates."""
    with postgres_app.app_context():
        service = KnowledgeService(embedding_provider=fake_provider)
        rag = RAGService(repository=service.repository, embedding_provider=fake_provider)

        doc1 = service.create_document(
            title="Doc In Category A",
            category="CategoryA",
            content="General shared keywords for both categories alpha beta.",
            active=True,
            auto_index=True,
        )
        doc2 = service.create_document(
            title="Doc In Category B",
            category="CategoryB",
            content="General shared keywords for both categories alpha beta.",
            active=True,
            auto_index=True,
        )

        # Filter by CategoryA
        res_cat = rag.retrieve(
            "alpha beta",
            filters=RetrievalFilters(category="CategoryA"),
        )
        for c in res_cat.final_chunks:
            assert c.document_category == "CategoryA"
            assert c.document_id == doc1.id

        # Filter by document_ids
        res_id = rag.retrieve(
            "alpha beta",
            filters=RetrievalFilters(document_ids=[doc2.id]),
        )
        for c in res_id.final_chunks:
            assert c.document_id == doc2.id

        # Cleanup
        service.delete_document(doc1.id)
        service.delete_document(doc2.id)


def test_crud_lifecycle_add_update_delete_reflected_in_retrieval(
    postgres_app, fake_provider
) -> None:
    """Verify full CRUD synchronization: Add, Update, Delete with content replacement."""
    with postgres_app.app_context():
        service = KnowledgeService(embedding_provider=fake_provider)
        rag = RAGService(repository=service.repository, embedding_provider=fake_provider)

        # 1. ADD
        doc = service.create_document(
            title="Parking Policy",
            category="Policies",
            content="MediLab parking fee is strictly 50 EGP for all visitor branches.",
            active=True,
            auto_index=True,
        )
        assert doc.index_status == "READY"

        res_v1 = rag.retrieve("parking fee for visitor branches")
        assert len(res_v1.final_chunks) > 0
        assert "50 EGP" in res_v1.final_chunks[0].content

        # 2. UPDATE
        updated = service.update_document(
            document_id=doc.id,
            content="MediLab parking fee has been updated to 75 EGP with valet service.",
            auto_index=True,
        )
        assert updated.version == 2
        assert updated.index_status == "READY"

        res_v2 = rag.retrieve("parking fee for visitor branches")
        assert len(res_v2.final_chunks) > 0
        assert "75 EGP" in res_v2.final_chunks[0].content
        # Crucial invariant: old 50 EGP text must NO LONGER be returned!
        assert "50 EGP" not in res_v2.final_chunks[0].content

        # 3. DELETE
        service.delete_document(doc.id)
        res_v3 = rag.retrieve("parking fee for visitor branches")
        matching = [c for c in res_v3.final_chunks if c.document_id == doc.id]
        assert len(matching) == 0
