"""CLI utility for safely re-indexing MediLab knowledge documents.

Canonical PDF-backed documents are always routed through PdfKnowledgeIngestionService so
section/page provenance cannot be destroyed by the legacy plain-text chunker.

Usage:
    uv run python scripts/reindex_knowledge.py --all
    uv run python scripts/reindex_knowledge.py --document-id 1
    uv run python scripts/reindex_knowledge.py --failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from app import create_app
from app.rag.embeddings import get_embedding_provider
from app.rag.ingestion import PdfKnowledgeIngestionService
from app.services.knowledge_service import KnowledgeService


def main() -> int:
    parser = argparse.ArgumentParser(description="MediLab AI Knowledge Base Re-Indexing")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Re-index all active knowledge documents")
    group.add_argument("--document-id", type=int, help="Re-index a specific document by its ID")
    group.add_argument(
        "--failed",
        action="store_true",
        help="Re-index only documents currently marked FAILED",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        provider = get_embedding_provider(app.config)
        service = KnowledgeService(embedding_provider=provider)
        pdf_service = PdfKnowledgeIngestionService(embedding_provider=provider)

        manifest = pdf_service.load_manifest()
        pdf_entries_by_title = {
            entry["title"]: entry for entry in manifest if entry.get("rag_use", True)
        }

        print("=" * 72)
        print("MediLab AI — Safe Knowledge Base Re-Indexing")
        print("=" * 72)
        print(f"Environment:       {app.config.get('MEDILAB_ENV', 'development')}")
        print(
            f"Embedding Model:   {app.config.get('EMBEDDING_MODEL')} "
            f"({app.config.get('EMBEDDING_DIMENSION')} dim)"
        )
        print("-" * 72)

        def reindex_one(doc):
            entry = pdf_entries_by_title.get(doc.title)
            if entry is not None:
                print(f'PDF reindex: id={doc.id} "{doc.title}"')
                indexed, status, detail = pdf_service.ingest_from_manifest_entry(
                    entry,
                    force=True,
                )
                return indexed, status, detail.get("chunks_count", 0), "pdf"

            print(f'Plain-text reindex: id={doc.id} "{doc.title}"')
            indexed = service.reindex_document(doc.id)
            chunks = service.repository.get_chunks_by_document(indexed.id)
            return indexed, "REINDEXED", len(chunks), "plain_text"

        if args.document_id:
            doc = service.get_document(args.document_id)
            if doc is None:
                print(f"ERROR: KnowledgeDocument id={args.document_id} not found.")
                return 1
            try:
                indexed, status, chunk_count, source_kind = reindex_one(doc)
                print(
                    f"SUCCESS: Document {indexed.id} -> {status}; "
                    f"source={source_kind}; chunks={chunk_count}; "
                    f"status={indexed.index_status}."
                )
            except Exception as exc:
                print(f"ERROR: Reindexing failed: {exc}")
                return 1
        else:
            status_filter = "FAILED" if args.failed else None
            docs = service.list_documents(active=True, index_status=status_filter)
            counts = {"total": len(docs), "indexed": 0, "failed": 0, "pdf": 0, "plain_text": 0}

            mode_desc = "failed documents only" if args.failed else "all active documents"
            print(f"Starting safe batch reindex ({mode_desc})...")
            for doc in docs:
                try:
                    _indexed, _status, _chunk_count, source_kind = reindex_one(doc)
                    counts["indexed"] += 1
                    counts[source_kind] += 1
                except Exception as exc:
                    counts["failed"] += 1
                    print(f"ERROR: document id={doc.id} failed: {exc}")

            print("-" * 72)
            print("Batch Reindexing Complete:")
            print(f"  Total Candidates:  {counts['total']}")
            print(f"  Successfully Done: {counts['indexed']}")
            print(f"  PDF-backed:        {counts['pdf']}")
            print(f"  Plain-text:        {counts['plain_text']}")
            print(f"  Failed:            {counts['failed']}")
            print("-" * 72)
            if counts["failed"]:
                return 1

    print("=" * 72)
    print("Reindexing operation completed successfully.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
