"""CLI utility for indexing and re-indexing KnowledgeDocuments in MediLab AI.

Usage:
    uv run python scripts/reindex_knowledge.py --all
    uv run python scripts/reindex_knowledge.py --document-id 1
    uv run python scripts/reindex_knowledge.py --failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from app import create_app
from app.rag.embeddings import JinaEmbeddingProvider
from app.services.knowledge_service import KnowledgeService


def main() -> int:
    parser = argparse.ArgumentParser(description="MediLab AI Knowledge Reindexing Utility")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Re-index all active knowledge documents")
    group.add_argument("--document-id", type=int, help="Re-index a specific document by its ID")
    group.add_argument(
        "--failed", action="store_true", help="Re-index only previously failed documents"
    )

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        api_key = app.config.get("JINA_API_KEY", "")
        model = app.config.get("EMBEDDING_MODEL", "jina-embeddings-v3")
        dimension = app.config.get("EMBEDDING_DIMENSION", 384)

        provider = JinaEmbeddingProvider(
            api_key=api_key,
            model=model,
            dimension=dimension,
        )
        service = KnowledgeService(embedding_provider=provider)

        print("=" * 65)
        print("MediLab AI — Knowledge Base Re-Indexing")
        print("=" * 65)
        print(f"Environment:       {app.config.get('APP_ENV')}")
        print(f"Database Target:   {app.config.get('SQLALCHEMY_DATABASE_URI', '').split('@')[-1]}")
        print(f"Embedding Model:   {model} ({dimension} dim)")
        print("-" * 65)

        if args.document_id:
            doc = service.get_document(args.document_id)
            if doc is None:
                print(f"ERROR: KnowledgeDocument id={args.document_id} not found.")
                return 1
            print(f'Re-indexing document id={doc.id}: "{doc.title}" (v{doc.version})...')
            try:
                indexed = service.reindex_document(doc.id)
                print(f"SUCCESS: Document {indexed.id} status is now {indexed.index_status}.")
                chunks = service.repository.get_chunks_by_document(indexed.id)
                print(f"         Generated {len(chunks)} chunks with 384-dim embeddings.")
            except Exception as exc:
                print(f"ERROR: Reindexing failed: {exc}")
                return 1

        elif args.failed or args.all:
            only_failed = args.failed
            mode_desc = "failed documents only" if only_failed else "all active documents"
            print(f"Starting batch reindex ({mode_desc})...")
            try:
                counts = service.reindex_all(only_failed=only_failed)
                print("-" * 65)
                print("Batch Reindexing Complete:")
                print(f"  Total Candidates:  {counts['total']}")
                print(f"  Successfully Done: {counts['indexed']}")
                print(f"  Failed:            {counts['failed']}")
                print("-" * 65)
                if counts["failed"] > 0:
                    print("WARNING: Some documents failed indexing. Run with --failed to retry.")
                    return 1
            except Exception as exc:
                print(f"FATAL ERROR during batch reindex: {exc}")
                return 1

    print("=" * 65)
    print("Reindexing operation completed successfully.")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
