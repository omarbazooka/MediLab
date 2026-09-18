"""MediLab AI — Production PDF Knowledge Ingestion CLI.

Ingests, validates, chunks, and embeds MediLab PDF documents into PostgreSQL/pgvector
storage using structure-aware parsing and Jina AI embeddings.

Usage:
    uv run python scripts/ingest_knowledge_pdfs.py --all
    uv run python scripts/ingest_knowledge_pdfs.py --file knowledge/pdfs/01_Patient_Test_Preparation_and_Specimen_Collection_Guide.pdf
    uv run python scripts/ingest_knowledge_pdfs.py --all --dry-run
    uv run python scripts/ingest_knowledge_pdfs.py --all --force
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure repository root is on sys.path
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


def mask_database_url(url: str | None) -> str:
    """Mask credentials in database connection string for safe display."""
    if not url:
        return "None"
    import re

    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MediLab AI — Structure-Aware PDF Knowledge Corpus Ingestion CLI"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Ingest all PDF documents defined in knowledge_manifest.json",
    )
    group.add_argument(
        "--file",
        type=str,
        help="Ingest a specific PDF file path",
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Custom path to knowledge_manifest.json (defaults to knowledge/knowledge_manifest.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and structure-chunk without writing to DB or invoking embedding API",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-indexing even if content SHA-256 hash is unchanged",
    )

    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        db_target = mask_database_url(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        provider_name = app.config.get("EMBEDDING_PROVIDER", "jina")
        model = app.config.get("EMBEDDING_MODEL", "jina-embeddings-v3")
        dim = app.config.get("EMBEDDING_DIMENSION", 384)

        print("=" * 78)
        print("MediLab AI — PDF Knowledge Ingestion CLI")
        print("=" * 78)
        print(f"Environment:       {app.config.get('MEDILAB_ENV', 'development')}")
        print(f"Database Target:   {db_target}")
        print(f"Embedding Model:   {model} ({dim} dim, provider={provider_name})")
        print(f"Dry Run:           {args.dry_run}")
        print(f"Force Re-index:    {args.force}")
        print("-" * 78)

        # Initialize ingestion service
        try:
            embedding_provider = get_embedding_provider()
            service = PdfKnowledgeIngestionService(
                embedding_provider=embedding_provider,
                manifest_path=args.manifest,
            )
        except Exception as exc:
            print(f"[ERROR] Service initialization failed: {exc}", file=sys.stderr)
            return 1

        start_time = time.perf_counter()

        if args.file:
            target_path = Path(args.file).resolve()
            print(f"Ingesting single document: {target_path.name}")
            try:
                doc, status, detail = service.ingest_pdf_file(
                    file_path=target_path,
                    dry_run=args.dry_run,
                    force=args.force,
                )
                elapsed = (time.perf_counter() - start_time) * 1000
                print("-" * 78)
                print(f"Status:            {status}")
                print(f"Document ID:       {detail.get('document_id', 'N/A')}")
                print(f"Title:             {detail.get('title')}")
                print(f"Sections Detected: {detail.get('sections_count', 'N/A')}")
                print(f"Chunks Produced:   {detail.get('chunks_count')}")
                print(f"Pages:             {detail.get('pages')}")
                print(f"Elapsed Time:      {elapsed:.1f}ms")
                print("=" * 78)
                return 0
            except Exception as exc:
                print(f"[ERROR] Ingestion failed for '{target_path.name}': {exc}", file=sys.stderr)
                return 1

        elif args.all:
            print("Starting batch ingestion from manifest...")
            try:
                batch_res = service.ingest_all(dry_run=args.dry_run, force=args.force)
                counts = batch_res["counts"]
                results = batch_res["results"]
                elapsed = (time.perf_counter() - start_time) * 1000

                print("-" * 78)
                print(f"{'Source File':<42} | {'Status':<10} | {'Chunks':<6} | {'Doc ID':<6}")
                print("-" * 78)
                for r in results:
                    src = r["source_file"]
                    stat = r["status"]
                    dtl = r.get("detail", {})
                    chunks = str(dtl.get("chunks_count", "-"))
                    doc_id = str(dtl.get("document_id", "-"))
                    print(f"{src[:42]:<42} | {stat:<10} | {chunks:<6} | {doc_id:<6}")
                print("-" * 78)
                print(
                    f"Summary: Total={counts['total']}, Ingested={counts['ingested']}, "
                    f"Updated={counts['updated']}, Unchanged={counts['unchanged']}, "
                    f"Failed={counts['failed']}"
                )
                print(f"Total Elapsed Time: {elapsed:.1f}ms")
                print("=" * 78)

                if counts["failed"] > 0:
                    return 1
                return 0
            except Exception as exc:
                print(f"[ERROR] Batch ingestion failed: {exc}", file=sys.stderr)
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
