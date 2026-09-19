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
        # Keep provider lazy so parser/manifest inspection and --dry-run do not require Jina credentials.
        self.embedding_provider = embedding_provider
        self.parser = PdfParser()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        base_dir = Path(__file__).resolve().parent.parent.parent
        self.manifest_path = (
            Path(manifest_path).resolve()
            if manifest_path
            else (base_dir / "knowledge" / "knowledge_manifest.json")
        )
        self.pdfs_dir = Path(pdfs_dir).resolve() if pdfs_dir else (base_dir / "knowledge" / "pdfs")

    def _get_embedding_provider(self) -> EmbeddingProvider:
        if self.embedding_provider is None:
            self.embedding_provider = get_embedding_provider()
        return self.embedding_provider

    @staticmethod
    def _sanitize_error(exc: Exception) -> str:
        raw_err = str(exc)
        safe_err = re.sub(
            r"(Bearer\s+)[a-zA-Z0-9_\-]+",
            r"\1[REDACTED]",
            raw_err,
            flags=re.I,
        )
        safe_err = re.sub(
            r"postgresql(?:\+psycopg)?://[^@]+@",
            "postgresql://[REDACTED]@",
            safe_err,
        )
        return safe_err[:400]

    def load_manifest(self) -> list[dict[str, Any]]:
        """Load and validate the knowledge manifest JSON."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Knowledge manifest not found at: {self.manifest_path}")

        with open(self.manifest_path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(f"Knowledge manifest at {self.manifest_path} must be a JSON array.")

        source_files: set[str] = set()
        titles: set[str] = set()
        for idx, entry in enumerate(data):
            for req_field in ("source_file", "title", "category"):
                if req_field not in entry or not str(entry[req_field]).strip():
                    raise ValueError(
                        f"Manifest entry #{idx} is missing required field '{req_field}'."
                    )

            source_file = str(entry["source_file"]).strip()
            title = str(entry["title"]).strip()
            if source_file in source_files:
                raise ValueError(f"Duplicate source_file in knowledge manifest: '{source_file}'.")
            if title in titles:
                raise ValueError(f"Duplicate title in knowledge manifest: '{title}'.")
            source_files.add(source_file)
            titles.add(title)

        return data

    def find_manifest_entry(self, file_path: str | Path) -> dict[str, Any]:
        """Resolve a canonical manifest entry by source filename.

        Single-file ingestion of the repository corpus must use manifest metadata so a PDF
        cannot silently become a second document with category='General'.
        """
        resolved_path = Path(file_path).resolve()
        source_name = resolved_path.name
        for entry in self.load_manifest():
            if entry["source_file"] == source_name:
                if not entry.get("rag_use", True):
                    raise ValueError(
                        f"Source PDF '{source_name}' is declared in the manifest but is not enabled for RAG."
                    )
                canonical_path = (self.pdfs_dir / source_name).resolve()
                if resolved_path != canonical_path:
                    raise ValueError(
                        f"Source PDF '{source_name}' must be ingested from the canonical corpus path: "
                        f"{canonical_path}"
                    )
                return entry
        raise ValueError(
            f"Source PDF '{source_name}' is not declared in {self.manifest_path.name}. "
            "Add it to the manifest before ingestion."
        )

    def _record_failed_attempt(
        self,
        document_id: int | None,
        previous_status: str | None,
        had_usable_chunks: bool,
        safe_err: str,
    ) -> None:
        """Record a failed indexing attempt without destroying a previously usable READY index."""
        if document_id is None:
            return

        try:
            doc = db.session.get(KnowledgeDocument, document_id)
            if doc is None:
                return

            if previous_status == "READY" and had_usable_chunks:
                # Preserve last-known-good retrieval. The failed refresh is observable via index_error,
                # while the previous version/chunks remain authoritative and retrievable.
                doc.index_status = "READY"
                doc.index_error = safe_err
            else:
                doc.index_status = "FAILED"
                doc.index_error = safe_err
            db.session.commit()
        except Exception:
            db.session.rollback()

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
        """Ingest a single PDF with structure-aware parsing and safe index replacement.

        Existing READY documents keep their previous content/chunks available until parsing,
        chunking, and embeddings for the replacement are ready. A failed refresh therefore
        cannot take the last-known-good index offline.

        Returns:
            tuple: (document or None, status_str, detail_dict)
            status_str is one of: INGESTED, UPDATED, UNCHANGED, DRY_RUN.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {path}")

        parsed_doc: ParsedDocument = self.parser.parse(path, title=title)
        effective_title = title.strip() if title else parsed_doc.title
        effective_category = category.strip()
        file_hash = parsed_doc.file_hash

        existing_doc = db.session.execute(
            db.select(KnowledgeDocument).where(KnowledgeDocument.title == effective_title)
        ).scalar_one_or_none()

        existing_chunks = (
            self.repository.get_chunks_by_document(existing_doc.id) if existing_doc else []
        )
        existing_hash = (
            (existing_chunks[0].metadata_ or {}).get("content_hash") if existing_chunks else None
        )
        metadata_changed = bool(
            existing_doc
            and (existing_doc.category != effective_category or existing_doc.active != active)
        )

        is_update = existing_doc is not None
        target_version = existing_doc.version + 1 if existing_doc else version

        # Dry-run is strictly read-only and always validates structure-aware chunking,
        # even when the current stored hash already matches the source file.
        if dry_run:
            dry_specs = chunk_parsed_document(
                parsed_doc=parsed_doc,
                document_id=existing_doc.id if existing_doc else 0,
                document_version=target_version,
                category=effective_category,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            return (
                None,
                "DRY_RUN",
                {
                    "document_id": existing_doc.id if existing_doc else None,
                    "title": effective_title,
                    "target_version": target_version,
                    "sections_count": len(parsed_doc.sections),
                    "chunks_count": len(dry_specs),
                    "pages": parsed_doc.total_pages,
                    "hash": file_hash,
                },
            )

        if (
            existing_doc
            and not force
            and existing_doc.index_status == "READY"
            and existing_hash == file_hash
            and not metadata_changed
        ):
            logger.info(
                "Document '%s' (id=%d) unchanged (hash=%s). Skipping.",
                effective_title,
                existing_doc.id,
                file_hash[:12],
            )
            if existing_doc.index_error:
                existing_doc.index_error = None
                db.session.commit()
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

        previous_status = existing_doc.index_status if existing_doc else None
        previous_doc_id = existing_doc.id if existing_doc else None
        had_usable_chunks = bool(existing_chunks and previous_status == "READY")

        try:
            if existing_doc is None:
                # New documents have no last-known-good index to preserve. Persist an INDEXING
                # lifecycle record first so a provider failure can be surfaced as FAILED.
                doc = KnowledgeDocument(
                    title=effective_title,
                    category=effective_category,
                    content=parsed_doc.raw_text,
                    active=active,
                    version=version,
                    index_status="INDEXING",
                )
                db.session.add(doc)
                db.session.commit()
                previous_doc_id = doc.id
            else:
                doc = existing_doc

            chunk_specs = chunk_parsed_document(
                parsed_doc=parsed_doc,
                document_id=doc.id,
                document_version=target_version,
                category=effective_category,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            if not chunk_specs:
                raise KnowledgeIndexingError(f"PDF '{path.name}' produced zero indexable chunks.")

            texts = [chunk["content"] for chunk in chunk_specs]
            embeddings = self._get_embedding_provider().embed_documents(texts)

            # Do not mutate an existing READY document until replacement embeddings exist.
            # The document update and chunk replacement then commit atomically.
            doc.version = target_version
            doc.content = parsed_doc.raw_text
            doc.category = effective_category
            doc.active = active
            doc.index_status = "INDEXING"
            doc.index_error = None

            self.repository.replace_document_chunks(
                document_id=doc.id,
                chunk_specs=chunk_specs,
                embeddings=embeddings,
            )

            doc.index_status = "READY"
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
            safe_err = self._sanitize_error(exc)
            logger.error("Failed ingesting PDF '%s': %s", path.name, safe_err)
            self._record_failed_attempt(
                document_id=previous_doc_id,
                previous_status=previous_status,
                had_usable_chunks=had_usable_chunks,
                safe_err=safe_err,
            )
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

        if not entry.get("rag_use", True):
            raise ValueError(f"Source PDF '{source_file}' is disabled for RAG in the manifest.")

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
        """Ingest all RAG-enabled documents declared in the manifest."""
        manifest = [entry for entry in self.load_manifest() if entry.get("rag_use", True)]
        results: list[dict[str, Any]] = []
        counts = {
            "total": len(manifest),
            "ingested": 0,
            "updated": 0,
            "unchanged": 0,
            "dry_run": 0,
            "failed": 0,
        }

        for entry in manifest:
            source_file = entry.get("source_file", "unknown")
            try:
                _doc, status, detail = self.ingest_from_manifest_entry(
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
                elif status == "DRY_RUN":
                    counts["dry_run"] += 1

                results.append({"source_file": source_file, "status": status, "detail": detail})
            except Exception as exc:
                counts["failed"] += 1
                results.append({"source_file": source_file, "status": "FAILED", "error": str(exc)})
                logger.exception("Failed ingesting manifest entry: %s", source_file)

        return {"counts": counts, "results": results}
