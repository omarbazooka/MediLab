"""PostgreSQL integration tests for PDF Knowledge Ingestion & Structure-Aware RAG.

Validates:
- End-to-end PDF ingestion into real PostgreSQL via PdfKnowledgeIngestionService
- Structure-aware chunking and persistence with VECTOR(384) embeddings
- PostgreSQL FTS search_vector trigger maintenance for PDF chunks
- Page and section provenance in chunk metadata (source_file, section_title, page_start, page_end)
- Hybrid retrieval via RAGService returning rich source_metadata
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest

from app.extensions import db
from app.rag.embeddings import DeterministicFakeEmbeddingProvider
from app.rag.indexing import KnowledgeIndexingError, KnowledgeIndexService
from app.rag.ingestion import PdfKnowledgeIngestionService
from app.rag.service import RAGService
from app.rag.types import RetrievalOutcome
from app.repositories.knowledge_repository import KnowledgeRepository
from scripts.seed_db import seed_knowledge_documents

pytestmark = pytest.mark.postgres


@pytest.fixture
def fake_provider() -> DeterministicFakeEmbeddingProvider:
    return DeterministicFakeEmbeddingProvider(dimension=384)


@pytest.fixture(autouse=True)
def clean_postgres_knowledge_tables(postgres_app):
    """Ensure disposable test database has clean knowledge tables before and after each test."""
    with postgres_app.app_context():
        db.session.rollback()
        db.session.execute(db.text("DELETE FROM knowledge_chunks;"))
        db.session.execute(db.text("DELETE FROM knowledge_documents;"))
        db.session.commit()
    yield
    with postgres_app.app_context():
        db.session.rollback()
        db.session.execute(db.text("DELETE FROM knowledge_chunks;"))
        db.session.execute(db.text("DELETE FROM knowledge_documents;"))
        db.session.commit()


@pytest.fixture
def small_sample_pdf(tmp_path) -> str:
    """Create a minimal structured 2-page PDF fixture for integration testing."""
    pdf_path = str(tmp_path / "08_Integration_Test_Guide.pdf")
    doc = fitz.open()

    # Page 1: Title + Section 1
    page1 = doc.new_page()
    page1.insert_text((50, 50), "MEDILAB", fontsize=14)
    page1.insert_text((50, 80), "Clinical Protocol Guide", fontsize=16)
    page1.insert_text((50, 110), "Knowledge Base Category: Laboratory Protocol", fontsize=10)
    page1.insert_text((50, 140), "1. Purpose and Clinical Scope", fontsize=12)
    page1.insert_text(
        (50, 170),
        "This document governs specimen collection protocols for diagnostic blood testing.",
        fontsize=10,
    )

    # Page 2: Section 2
    page2 = doc.new_page()
    page2.insert_text((50, 50), "2. Fasting and Sample Collection Protocol", fontsize=12)
    page2.insert_text(
        (50, 80),
        "Patients must fast for exactly 10 to 12 hours prior to metabolic panel blood draws.",
        fontsize=10,
    )
    page2.insert_text(
        (50, 110),
        "Water consumption is permitted during the fasting interval to maintain adequate hydration.",
        fontsize=10,
    )

    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_postgres_pdf_ingestion_and_hybrid_retrieval(
    postgres_app, fake_provider, small_sample_pdf
) -> None:
    """Test full pipeline: parse PDF -> chunk -> embed -> persist -> FTS + semantic search in PostgreSQL."""
    with postgres_app.app_context():
        repo = KnowledgeRepository()
        ingestion_service = PdfKnowledgeIngestionService(
            repository=repo,
            embedding_provider=fake_provider,
        )

        doc, status, detail = ingestion_service.ingest_pdf_file(
            file_path=small_sample_pdf,
            title="Clinical Protocol Guide",
            category="Preparation",
            version=1,
            force=True,
        )

        try:
            assert doc is not None
            assert doc.index_status == "READY"
            assert doc.title == "Clinical Protocol Guide"

            # Verify chunks in database
            chunks = repo.get_chunks_by_document(doc.id)
            assert len(chunks) >= 2

            # Check that section titles and provenance are properly mapped
            section_titles = [c.metadata_["section_title"] for c in chunks]
            assert any("Purpose" in t for t in section_titles)
            assert any("Fasting" in t for t in section_titles)

            fasting_chunks = [c for c in chunks if "Fasting" in c.metadata_["section_title"]]
            assert len(fasting_chunks) > 0
            fasting_chunk = fasting_chunks[0]

            assert fasting_chunk.metadata_["source_type"] == "pdf"
            assert fasting_chunk.metadata_["source_file"].endswith("08_Integration_Test_Guide.pdf")
            assert fasting_chunk.metadata_["page_start"] == 2
            assert fasting_chunk.metadata_["document_version"] == 1
            assert "content_hash" in fasting_chunk.metadata_

            # Verify FTS search_vector trigger populated
            assert fasting_chunk.search_vector is not None
            lex_results = repo.search_lexical("metabolic panel hydration", top_k=5)
            assert any(c.chunk_id == fasting_chunk.id for c in lex_results)

            # Verify semantic search in PostgreSQL pgvector
            query_vec = fake_provider.embed_query("metabolic panel fasting hours")
            sem_results = repo.search_semantic(query_vec, top_k=5)
            assert any(c.chunk_id == fasting_chunk.id for c in sem_results)

            # Verify end-to-end RAGService retrieval returns source provenance
            rag = RAGService(repository=repo, embedding_provider=fake_provider)
            retrieval_result = rag.retrieve(
                "How many hours fasting for metabolic panel blood draws?"
            )
            assert retrieval_result.outcome == RetrievalOutcome.GOOD.value
            assert len(retrieval_result.final_chunks) > 0

            top_chunk = retrieval_result.final_chunks[0]
            assert top_chunk.document_id == doc.id
            assert top_chunk.source_metadata is not None
            assert top_chunk.source_metadata["source_type"] == "pdf"
            assert top_chunk.source_metadata["page_start"] == 2
            assert "Fasting" in top_chunk.source_metadata["section_title"]
            assert top_chunk.source_metadata["source_file"].endswith(
                "08_Integration_Test_Guide.pdf"
            )

        finally:
            # Cleanup
            repo.delete_document(doc)
            db.session.commit()


def test_plain_indexer_refuses_pdf_managed_document(
    postgres_app, fake_provider, small_sample_pdf
) -> None:
    """The legacy text indexer must not erase section/page provenance from PDF chunks."""
    with postgres_app.app_context():
        repo = KnowledgeRepository()
        ingestion_service = PdfKnowledgeIngestionService(
            repository=repo,
            embedding_provider=fake_provider,
        )
        doc, _, _ = ingestion_service.ingest_pdf_file(
            file_path=small_sample_pdf,
            title="PDF Guard Integration Guide",
            category="Preparation",
            force=True,
        )

        try:
            before = [
                (chunk.id, chunk.content, chunk.metadata_.copy())
                for chunk in repo.get_chunks_by_document(doc.id)
            ]
            indexer = KnowledgeIndexService(
                repository=repo,
                embedding_provider=fake_provider,
            )
            with pytest.raises(KnowledgeIndexingError, match="PDF-managed"):
                indexer.index_document(doc.id)

            db.session.expire_all()
            preserved = repo.get_document_by_id(doc.id)
            after = [
                (chunk.id, chunk.content, chunk.metadata_.copy())
                for chunk in repo.get_chunks_by_document(doc.id)
            ]
            assert preserved.index_status == "READY"
            assert after == before
        finally:
            repo.delete_document(repo.get_document_by_id(doc.id))
            db.session.commit()


def test_seed_preserves_canonical_pdf_content_and_chunks(postgres_app, fake_provider) -> None:
    """Running database seed after live PDF ingestion must not replace PDF text with placeholders."""
    repo_root = Path(__file__).resolve().parents[2]
    pdf_path = (
        repo_root
        / "knowledge"
        / "pdfs"
        / "01_Patient_Test_Preparation_and_Specimen_Collection_Guide.pdf"
    )

    with postgres_app.app_context():
        repo = KnowledgeRepository()
        ingestion_service = PdfKnowledgeIngestionService(
            repository=repo,
            embedding_provider=fake_provider,
        )
        doc, _, _ = ingestion_service.ingest_pdf_file(
            file_path=pdf_path,
            title="Patient Test Preparation & Specimen Collection Guide",
            category="Preparation",
            force=True,
        )
        original_content = doc.content
        original_version = doc.version
        original_chunks = [
            (chunk.id, chunk.content, chunk.metadata_.copy())
            for chunk in repo.get_chunks_by_document(doc.id)
        ]

        seed_knowledge_documents()
        db.session.commit()
        db.session.expire_all()

        preserved = repo.get_document_by_id(doc.id)
        preserved_chunks = [
            (chunk.id, chunk.content, chunk.metadata_.copy())
            for chunk in repo.get_chunks_by_document(doc.id)
        ]
        assert preserved.content == original_content
        assert preserved.version == original_version
        assert preserved.index_status == "READY"
        assert preserved_chunks == original_chunks


def test_seed_does_not_deactivate_custom_knowledge(postgres_app) -> None:
    """Canonical seed sync must not disable future CRUD/admin knowledge outside the PDF manifest."""
    with postgres_app.app_context():
        repo = KnowledgeRepository()
        custom = repo.create_document(
            title="Custom Admin FAQ",
            category="FAQ",
            content="Custom operational knowledge added through a future admin workflow.",
            active=True,
            index_status="PENDING",
        )
        db.session.commit()

        seed_knowledge_documents()
        db.session.commit()
        db.session.expire_all()

        preserved = repo.get_document_by_id(custom.id)
        assert preserved is not None
        assert preserved.active is True
        assert preserved.title == "Custom Admin FAQ"


def test_safe_reindex_routing_pdf_and_plain_text(postgres_app, fake_provider) -> None:
    """Verify safe reindex routing: canonical PDF routes to PdfKnowledgeIngestionService and plain text routes to KnowledgeIndexService."""
    from app.services.knowledge_service import KnowledgeService

    with postgres_app.app_context():
        repo = KnowledgeRepository()
        pdf_service = PdfKnowledgeIngestionService(
            repository=repo,
            embedding_provider=fake_provider,
        )
        knowledge_service = KnowledgeService(
            repository=repo,
            embedding_provider=fake_provider,
        )

        manifest = pdf_service.load_manifest()
        first_pdf_entry = next(entry for entry in manifest if entry.get("rag_use", True))
        pdf_entries_by_title = {
            entry["title"]: entry for entry in manifest if entry.get("rag_use", True)
        }

        # 1. Ingest canonical PDF
        pdf_doc, _, _ = pdf_service.ingest_from_manifest_entry(first_pdf_entry, force=True)
        assert pdf_doc.index_status == "READY"
        pdf_chunks_before = repo.get_chunks_by_document(pdf_doc.id)
        assert len(pdf_chunks_before) > 0
        assert all(c.metadata_.get("source_type") == "pdf" for c in pdf_chunks_before)

        # 2. Create plain text document
        plain_doc = repo.create_document(
            title="Custom Clinic Hours FAQ",
            category="FAQ",
            content="MediLab clinics operate Saturday through Thursday from 8:00 AM to 10:00 PM.",
            active=True,
            index_status="PENDING",
        )
        db.session.commit()

        # 3. Simulate reindex_knowledge routing logic
        docs_to_reindex = [pdf_doc, plain_doc]
        routed = {}
        for doc in docs_to_reindex:
            entry = pdf_entries_by_title.get(doc.title)
            if entry is not None:
                indexed, status, detail = pdf_service.ingest_from_manifest_entry(entry, force=True)
                routed[doc.id] = ("pdf", status, detail.get("chunks_count", 0))
            else:
                indexed = knowledge_service.reindex_document(doc.id)
                chunks = repo.get_chunks_by_document(indexed.id)
                routed[doc.id] = ("plain_text", "REINDEXED", len(chunks))

        assert routed[pdf_doc.id][0] == "pdf"
        assert routed[plain_doc.id][0] == "plain_text"

        # Verify PDF document kept its rich PDF metadata and provenance
        db.session.expire_all()
        pdf_chunks_after = repo.get_chunks_by_document(pdf_doc.id)
        assert len(pdf_chunks_after) == len(pdf_chunks_before)
        for chunk in pdf_chunks_after:
            assert chunk.metadata_.get("source_type") == "pdf"
            assert "section_title" in chunk.metadata_
            assert "page_start" in chunk.metadata_

        # Verify plain-text document is indexed and READY
        plain_chunks = repo.get_chunks_by_document(plain_doc.id)
        assert len(plain_chunks) > 0
        assert repo.get_document_by_id(plain_doc.id).index_status == "READY"
