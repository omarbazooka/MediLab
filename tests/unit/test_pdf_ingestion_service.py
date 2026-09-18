"""Unit tests for PdfKnowledgeIngestionService."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.extensions import db
from app.rag.embeddings import DeterministicFakeEmbeddingProvider
from app.rag.indexing import KnowledgeIndexingError
from app.rag.ingestion import PdfKnowledgeIngestionService
from app.repositories.knowledge_repository import KnowledgeRepository


@pytest.fixture
def fake_pdf_corpus(tmp_path: Path) -> tuple[Path, Path]:
    """Create a temporary PDF file and manifest fixture."""
    corpus_dir = tmp_path / "pdfs"
    corpus_dir.mkdir(parents=True)

    pdf_file = corpus_dir / "01_test_prep.pdf"
    doc = fitz.open()

    p1 = doc.new_page()
    p1.insert_text(
        (50, 72),
        "MEDILAB\n\n"
        "Patient Test Preparation\n\n"
        "Guide\n\n"
        "Knowledge Base Category: Preparation\n\n"
        "1. Fasting\n"
        "Fast 10-12 hours for lipid profiles.",
    )

    doc.save(str(pdf_file))
    doc.close()

    manifest_file = tmp_path / "manifest.json"
    manifest_data = [
        {
            "source_file": "01_test_prep.pdf",
            "title": "Patient Test Preparation Guide",
            "category": "Preparation",
            "version": 1,
            "active": True,
        }
    ]
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    return corpus_dir, manifest_file


def test_manifest_loading_and_validation(fake_pdf_corpus, app):
    """Verify that knowledge manifest JSON loads and validates schema."""
    corpus_dir, manifest_file = fake_pdf_corpus
    service = PdfKnowledgeIngestionService(
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )
    entries = service.load_manifest()
    assert len(entries) == 1
    assert entries[0]["title"] == "Patient Test Preparation Guide"


def test_manifest_missing_required_field_raises(tmp_path: Path):
    """Verify that a malformed manifest missing required fields raises ValueError."""
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text(
        json.dumps([{"source_file": "01.pdf"}]),
        encoding="utf-8",  # missing title, category
    )
    service = PdfKnowledgeIngestionService(manifest_path=bad_manifest)
    with pytest.raises(ValueError, match="missing required field"):
        service.load_manifest()


def test_ingest_new_pdf_document(fake_pdf_corpus, app):
    """Verify ingestion of a new PDF creates KnowledgeDocument and chunks in READY status."""
    corpus_dir, manifest_file = fake_pdf_corpus
    repo = KnowledgeRepository()
    fake_embedder = DeterministicFakeEmbeddingProvider(dimension=384)

    service = PdfKnowledgeIngestionService(
        repository=repo,
        embedding_provider=fake_embedder,
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )

    with app.app_context():
        db.create_all()
        doc, status, detail = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
        )

        assert status == "INGESTED"
        assert doc is not None
        assert doc.index_status == "READY"
        assert doc.version == 1

        chunks = repo.get_chunks_by_document(doc.id)
        assert len(chunks) > 0
        assert chunks[0].embedding is not None
        assert len(chunks[0].embedding) == 384
        assert chunks[0].metadata_["source_type"] == "pdf"
        assert chunks[0].metadata_["source_file"] == "01_test_prep.pdf"


def test_ingest_unchanged_pdf_skips_reindexing(fake_pdf_corpus, app):
    """Verify that re-ingesting an unchanged PDF returns UNCHANGED without recreating chunks."""
    corpus_dir, manifest_file = fake_pdf_corpus
    repo = KnowledgeRepository()
    fake_embedder = DeterministicFakeEmbeddingProvider(dimension=384)

    service = PdfKnowledgeIngestionService(
        repository=repo,
        embedding_provider=fake_embedder,
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )

    with app.app_context():
        db.create_all()
        # First ingestion
        doc1, status1, _ = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
        )
        assert status1 == "INGESTED"

        # Second ingestion: should be detected as unchanged
        doc2, status2, detail2 = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
        )
        assert status2 == "UNCHANGED"
        assert doc2.id == doc1.id


def test_ingest_force_reindex_increments_version(fake_pdf_corpus, app):
    """Verify that force re-indexing an existing document increments version."""
    corpus_dir, manifest_file = fake_pdf_corpus
    repo = KnowledgeRepository()
    fake_embedder = DeterministicFakeEmbeddingProvider(dimension=384)

    service = PdfKnowledgeIngestionService(
        repository=repo,
        embedding_provider=fake_embedder,
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )

    with app.app_context():
        db.create_all()
        doc1, _, _ = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
        )
        assert doc1.version == 1

        # Force re-index
        doc2, status2, _ = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
            force=True,
        )
        assert status2 == "UPDATED"
        assert doc2.version == 2
        assert doc2.index_status == "READY"


def test_ingest_embedding_failure_sets_failed_status(fake_pdf_corpus, app):
    """Verify that an embedding provider error marks the document FAILED."""
    corpus_dir, manifest_file = fake_pdf_corpus
    repo = KnowledgeRepository()

    class FailingEmbeddingProvider:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("Jina API connection timeout with Bearer token_secret_12345")

        def embed_query(self, text: str) -> list[float]:
            return [0.0] * 384

    service = PdfKnowledgeIngestionService(
        repository=repo,
        embedding_provider=FailingEmbeddingProvider(),
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )

    with app.app_context():
        db.create_all()
        with pytest.raises(KnowledgeIndexingError):
            service.ingest_pdf_file(
                file_path=corpus_dir / "01_test_prep.pdf",
                title="Failing Ingestion Test",
                category="Preparation",
            )

        failed_doc = repo.list_documents(category="Preparation")
        matching = [d for d in failed_doc if d.title == "Failing Ingestion Test"]
        assert len(matching) == 1
        assert matching[0].index_status == "FAILED"
        # Verify secret was sanitized
        assert "token_secret_12345" not in matching[0].index_error
        assert "[REDACTED]" in matching[0].index_error
