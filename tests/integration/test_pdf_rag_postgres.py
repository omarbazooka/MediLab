"""PostgreSQL integration tests for PDF Knowledge Ingestion & Structure-Aware RAG.

Validates:
- End-to-end PDF ingestion into real PostgreSQL via PdfKnowledgeIngestionService
- Structure-aware chunking and persistence with VECTOR(384) embeddings
- PostgreSQL FTS search_vector trigger maintenance for PDF chunks
- Page and section provenance in chunk metadata (source_file, section_title, page_start, page_end)
- Hybrid retrieval via RAGService returning rich source_metadata
"""

from __future__ import annotations

import pymupdf as fitz
import pytest

from app.extensions import db
from app.rag.embeddings import DeterministicFakeEmbeddingProvider
from app.rag.ingestion import PdfKnowledgeIngestionService
from app.rag.service import RAGService
from app.rag.types import RetrievalOutcome
from app.repositories.knowledge_repository import KnowledgeRepository

pytestmark = pytest.mark.postgres


@pytest.fixture
def fake_provider() -> DeterministicFakeEmbeddingProvider:
    return DeterministicFakeEmbeddingProvider(dimension=384)


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
