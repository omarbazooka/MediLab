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


def test_dry_run_existing_document_is_strictly_read_only(fake_pdf_corpus, app):
    """Dry-run must not mutate an existing READY PDF document or its chunks."""
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
        doc, _, _ = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
        )
        original_version = doc.version
        original_content = doc.content
        original_status = doc.index_status
        original_chunk_ids = [chunk.id for chunk in repo.get_chunks_by_document(doc.id)]

        dry_doc, status, detail = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
            dry_run=True,
            force=True,
        )

        db.session.expire_all()
        reloaded = repo.get_document_by_id(doc.id)
        assert dry_doc is None
        assert status == "DRY_RUN"
        assert detail["document_id"] == doc.id
        assert reloaded.version == original_version
        assert reloaded.content == original_content
        assert reloaded.index_status == original_status == "READY"
        assert [chunk.id for chunk in repo.get_chunks_by_document(doc.id)] == original_chunk_ids


def test_failed_update_preserves_last_known_good_ready_index(fake_pdf_corpus, app):
    """A failed PDF refresh must not take a previously READY index offline."""
    corpus_dir, manifest_file = fake_pdf_corpus
    repo = KnowledgeRepository()
    good_provider = DeterministicFakeEmbeddingProvider(dimension=384)
    good_service = PdfKnowledgeIngestionService(
        repository=repo,
        embedding_provider=good_provider,
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )

    class FailingEmbeddingProvider:
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("Bearer update_secret_token provider unavailable")

        def embed_query(self, text: str) -> list[float]:
            return [0.0] * 384

    with app.app_context():
        db.create_all()
        doc, _, _ = good_service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
        )
        original_content = doc.content
        original_version = doc.version
        original_chunks = [
            (chunk.id, chunk.content, chunk.metadata_.copy())
            for chunk in repo.get_chunks_by_document(doc.id)
        ]

        # Change the source PDF so this is a real update attempt rather than UNCHANGED.
        pdf_path = corpus_dir / "01_test_prep.pdf"
        changed = fitz.open(str(pdf_path))
        changed[0].insert_text((50, 180), "Additional updated preparation guidance.")
        tmp_changed = corpus_dir / "changed.pdf"
        changed.save(str(tmp_changed))
        changed.close()
        pdf_path.unlink()
        tmp_changed.rename(pdf_path)

        failing_service = PdfKnowledgeIngestionService(
            repository=repo,
            embedding_provider=FailingEmbeddingProvider(),
            manifest_path=manifest_file,
            pdfs_dir=corpus_dir,
        )

        with pytest.raises(KnowledgeIndexingError):
            failing_service.ingest_pdf_file(
                file_path=pdf_path,
                title="Patient Test Preparation Guide",
                category="Preparation",
            )

        db.session.expire_all()
        preserved = repo.get_document_by_id(doc.id)
        assert preserved.index_status == "READY"
        assert preserved.version == original_version
        assert preserved.content == original_content
        assert preserved.index_error is not None
        assert "update_secret_token" not in preserved.index_error

        preserved_chunks = [
            (chunk.id, chunk.content, chunk.metadata_.copy())
            for chunk in repo.get_chunks_by_document(doc.id)
        ]
        assert preserved_chunks == original_chunks


def test_manifest_lookup_rejects_unknown_single_file(fake_pdf_corpus, tmp_path):
    """Single-file corpus ingestion must not silently bypass manifest metadata."""
    corpus_dir, manifest_file = fake_pdf_corpus
    service = PdfKnowledgeIngestionService(
        embedding_provider=DeterministicFakeEmbeddingProvider(dimension=384),
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )

    known = service.find_manifest_entry(corpus_dir / "01_test_prep.pdf")
    assert known["category"] == "Preparation"

    unknown = tmp_path / "unknown.pdf"
    unknown.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="not declared"):
        service.find_manifest_entry(unknown)


def test_manifest_metadata_change_is_not_misclassified_as_unchanged(fake_pdf_corpus, app):
    """Category/active changes must be applied even when source PDF bytes are unchanged."""
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
        doc, _, _ = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
            active=True,
        )
        updated, status, _ = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Policies",
            active=False,
        )

        assert status == "UPDATED"
        assert updated.version == 2
        assert updated.category == "Policies"
        assert updated.active is False


def test_dry_run_does_not_require_embedding_provider(fake_pdf_corpus, app, monkeypatch):
    """Parser/chunker dry-run must not construct or call the configured Jina provider."""
    corpus_dir, manifest_file = fake_pdf_corpus

    def fail_provider_factory():
        raise AssertionError("embedding provider must not be created during dry-run")

    monkeypatch.setattr("app.rag.ingestion.get_embedding_provider", fail_provider_factory)
    service = PdfKnowledgeIngestionService(
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )

    with app.app_context():
        db.create_all()
        doc, status, detail = service.ingest_pdf_file(
            file_path=corpus_dir / "01_test_prep.pdf",
            title="Patient Test Preparation Guide",
            category="Preparation",
            dry_run=True,
        )
        assert doc is None
        assert status == "DRY_RUN"
        assert detail["chunks_count"] > 0


def test_manifest_lookup_rejects_same_name_outside_canonical_directory(
    fake_pdf_corpus, tmp_path
):
    """A same-named external PDF must not impersonate a canonical manifest source."""
    corpus_dir, manifest_file = fake_pdf_corpus
    service = PdfKnowledgeIngestionService(
        embedding_provider=DeterministicFakeEmbeddingProvider(dimension=384),
        manifest_path=manifest_file,
        pdfs_dir=corpus_dir,
    )
    canonical = corpus_dir / "01_test_prep.pdf"
    spoof_dir = tmp_path / "outside"
    spoof_dir.mkdir()
    spoof = spoof_dir / canonical.name
    spoof.write_bytes(canonical.read_bytes())

    with pytest.raises(ValueError, match="canonical corpus path"):
        service.find_manifest_entry(spoof)
