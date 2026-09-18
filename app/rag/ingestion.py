"""Service orchestrating structure-aware PDF knowledge ingestion and lifecycle."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.extensions import db
from app.models.knowledge import KnowledgeDocument
from app.rag.chunking import PDF_CHUNK_OVERLAP, PDF_CHUNK_SIZE, chunk_parsed_document
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.indexing import KnowledgeIndexingError
from app.rag.parsers.pdf import ParsedDocument, PdfParser
from app.repositories.knowledge_repository import KnowledgeRepository

logger = logging.getLogger("medilab.rag.ingestion")


class PdfKnowledgeIngestionService:
    """Ingests, chunks, embeds, and synchronizes PDF documents against the database."""

    def __init__(
        self,
        repository: KnowledgeRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        manifest_path: str | Path | None = None,
        pdfs_dir: str | Path | None = None,
        chunk_size: int = PDF_CHUNK_SIZE,
        chunk_overlap: int = PDF_CHUNK_OVERLAP,
    ) -> None:
        self.repository = repository or KnowledgeRepository()
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.parser = PdfParser()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Base directories
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.manifest_path = (
            Path(manifest_path).resolve()
            if manifest_path
            else (base_dir / "knowledge" / "knowledge_manifest.json")
        )
        self.pdfs_dir = Path(pdfs_dir).resolve() if pdfs_dir else (base_dir / "knowledge" / "pdfs")

    def load_manifest(self) -> list[dict[str, Any]]:
        """Load and validate the knowledge manifest JSON."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Knowledge manifest not found at: {self.manifest_path}")

        with open(self.manifest_path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(f"Knowledge manifest at {self.manifest_path} must be a JSON array.")

        for idx, entry in enumerate(data):
            for req_field in ("source_file", "title", "category"):
                if req_field not in entry or not str(entry[req_field]).strip():
                    raise ValueError(
                        f"Manifest entry #{idx} is missing required field '{req_field}'."
                    )

        return data

    def ingest_pdf_file(
        self,
        file_path: str | Path,
        title: str | None = None,
        category: str = "General",
        version: int = 1,
        active: bool = True,
        dry_run: bool = False,
        force: bool = False,
    ) -> tuple[KnowledgeDocument | None, str, dict[str, Any]]:
        """Ingest a single PDF file with full structure-aware parsing, chunking, and embedding.

        Returns:
            tuple: (document or None, status_str, detail_dict)
            status_str is one of: "INGESTED", "UPDATED", "UNCHANGED", "DRY_RUN", "FAILED"
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {path}")

        parsed_doc: ParsedDocument = self.parser.parse(path, title=title)
        effective_title = title.strip() if title else parsed_doc.title
        file_hash = parsed_doc.file_hash

        # Check for existing document by title
        existing_doc = db.session.execute(
            db.select(KnowledgeDocument).where(KnowledgeDocument.title == effective_title)
        ).scalar_one_or_none()

        # Check if content is unchanged
        if existing_doc and not force:
            existing_chunks = self.repository.get_chunks_by_document(existing_doc.id)
            if existing_chunks and existing_doc.index_status == "READY":
                first_meta = existing_chunks[0].metadata_ or {}
                if first_meta.get("content_hash") == file_hash:
                    logger.info(
                        "Document '%s' (id=%d) unchanged (hash=%s). Skipping.",
                        effective_title,
                        existing_doc.id,
                        file_hash[:12],
                    )
                    return (
                        existing_doc,
                        "UNCHANGED",
                        {
                            "document_id": existing_doc.id,
                            "title": effective_title,
                            "chunks_count": len(existing_chunks),
                            "hash": file_hash,
                        },
                    )

        doc = existing_doc
        is_update = doc is not None

        if is_update:
            target_version = doc.version + 1
            doc.version = target_version
            doc.content = parsed_doc.raw_text
            doc.category = category.strip()
            doc.active = active
            doc.index_status = "INDEXING"
        else:
            doc = KnowledgeDocument(
                title=effective_title,
                category=category.strip(),
                content=parsed_doc.raw_text,
                active=active,
                version=version,
                index_status="INDEXING",
            )
            db.session.add(doc)

        db.session.commit()

        try:
            chunk_specs = chunk_parsed_document(
                parsed_doc=parsed_doc,
                document_id=doc.id,
                document_version=doc.version,
                category=doc.category,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )

            if dry_run:
                if not is_update:
                    # Clean up dry-run created doc
                    db.session.delete(doc)
                    db.session.commit()
                return (
                    None,
                    "DRY_RUN",
                    {
                        "title": effective_title,
                        "sections_count": len(parsed_doc.sections),
                        "chunks_count": len(chunk_specs),
                        "pages": parsed_doc.total_pages,
                        "hash": file_hash,
                    },
                )

            # Generate passage embeddings using configured provider
            texts = [c["content"] for c in chunk_specs]
            embeddings = self.embedding_provider.embed_documents(texts) if texts else []

            # Replace chunks transactionally
            self.repository.replace_document_chunks(
                document_id=doc.id,
                chunk_specs=chunk_specs,
                embeddings=embeddings,
            )

            # Transition status to READY
            doc.index_status = "READY"
            doc.index_error = None
            doc.last_indexed_at = datetime.now(UTC)
            db.session.commit()

            status_str = "UPDATED" if is_update else "INGESTED"
            logger.info(
                "Successfully %s document id=%d '%s' with %d chunks",
                status_str.lower(),
                doc.id,
                doc.title,
                len(chunk_specs),
            )
            return (
                doc,
                status_str,
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "version": doc.version,
                    "sections_count": len(parsed_doc.sections),
                    "chunks_count": len(chunk_specs),
                    "pages": parsed_doc.total_pages,
                    "hash": file_hash,
                },
            )

        except Exception as exc:
            db.session.rollback()
            raw_err = str(exc)
            safe_err = re.sub(r"(Bearer\s+)[a-zA-Z0-9_\-]+", r"\1[REDACTED]", raw_err, flags=re.I)
            safe_err = re.sub(
                r"postgresql(?:\+psycopg)?://[^@]+@", "postgresql://[REDACTED]@", safe_err
            )[:400]

            logger.error("Failed ingesting PDF '%s': %s", path.name, safe_err)
            if doc and doc.id:
                try:
                    self.repository.set_document_status(
                        document_id=doc.id,
                        status="FAILED",
                        error=safe_err,
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            raise KnowledgeIndexingError(
                f"PDF ingestion failed for '{path.name}': {safe_err}"
            ) from exc

    def ingest_from_manifest_entry(
        self,
        entry: dict[str, Any],
        dry_run: bool = False,
        force: bool = False,
    ) -> tuple[KnowledgeDocument | None, str, dict[str, Any]]:
        """Ingest a document specified by a manifest entry."""
        source_file = entry["source_file"]
        file_path = self.pdfs_dir / source_file

        if not file_path.exists():
            raise FileNotFoundError(
                f"Source PDF '{source_file}' listed in manifest was not found in: {self.pdfs_dir}"
            )

        return self.ingest_pdf_file(
            file_path=file_path,
            title=entry.get("title"),
            category=entry.get("category", "General"),
            version=entry.get("version", 1),
            active=entry.get("active", True),
            dry_run=dry_run,
            force=force,
        )

    def ingest_all(
        self,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        """Ingest all active documents declared in the manifest."""
        manifest = self.load_manifest()
        results: list[dict[str, Any]] = []
        counts = {"total": len(manifest), "ingested": 0, "updated": 0, "unchanged": 0, "failed": 0}

        for entry in manifest:
            source_file = entry.get("source_file", "unknown")
            try:
                doc, status, detail = self.ingest_from_manifest_entry(
                    entry,
                    dry_run=dry_run,
                    force=force,
                )
                if status == "INGESTED":
                    counts["ingested"] += 1
                elif status == "UPDATED":
                    counts["updated"] += 1
                elif status == "UNCHANGED":
                    counts["unchanged"] += 1

                results.append({"source_file": source_file, "status": status, "detail": detail})
            except Exception as exc:
                counts["failed"] += 1
                results.append({"source_file": source_file, "status": "FAILED", "error": str(exc)})
                logger.exception("Failed ingesting manifest entry: %s", source_file)

        return {"counts": counts, "results": results}
