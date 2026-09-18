# Phase 2 PDF Ingestion — Independent QA Hardening

## Scope

Classification: **Core Enhancement QA** inside required Phase 2 RAG.

This QA pass reviews the structure-aware PDF ingestion added after the standalone hybrid RAG core. It does not introduce LangGraph, UI upload, another vector database, or a new business-action scope.

## Baseline evidence

The PDF-ingestion implementation was initially committed in `a5d324a2d3b488426c5047fc55561385e499151c`.

Before the independent hardening commits, recorded execution evidence included:

- 116 unit tests passed.
- 23 PostgreSQL integration tests passed with zero skips.
- 139 full-suite tests passed.
- 7 PDF documents / 89 chunks were live-indexed with Jina embeddings.
- Live retrieval verification passed 6/6 cases.
- The 28-case benchmark recorded Recall@4 100%, MRR 0.9565, and no-answer accuracy 100%.

Those results are **historical evidence**. Later QA commits add regression tests and modify ingestion/reindex lifecycle behavior, so the final branch head requires a fresh runtime gate before Phase 2 can be marked complete.

## QA findings fixed

### 1. Dry-run mutation risk

The original PDF ingestion path updated document version/content/status before checking `dry_run` for existing documents.

Fix:
- dry-run is now strictly read-only;
- it always performs parse + structure-aware chunk validation;
- it performs no DB writes, version bumps, status changes, or embedding API calls.

Regression coverage was added.

### 2. Failed refresh could take a healthy index offline

The original update path committed `INDEXING` and the new document version before Jina embeddings were successfully produced.

Fix:
- an existing `READY` document is not mutated until replacement chunks/embeddings are prepared;
- document mutation + chunk replacement commit atomically;
- failed refreshes preserve the last-known-good READY version/chunks and record a sanitized `index_error`.

Regression coverage was added.

### 3. Single-file ingestion could bypass manifest metadata

The original `--file` path defaulted to generic metadata and could change a canonical document category.

Fix:
- canonical single-file ingestion resolves title/category/version/active from `knowledge_manifest.json`;
- unknown files are rejected;
- a same-named file outside the canonical corpus directory is rejected.

Regression coverage was added.

### 4. Seed could overwrite canonical PDF content

After PDF ingestion, `seed_db.py` could replace `KnowledgeDocument.content` with bootstrap placeholder text.

Fix:
- seed creates missing canonical records but never overwrites already-ingested PDF content;
- manifest metadata remains synchronizable without destroying PDF-owned content/chunks.

PostgreSQL regression coverage was added.

### 5. Seed could deactivate arbitrary future knowledge

The original manifest migration deactivated every active knowledge document not present in the seven-file corpus.

Fix:
- only the known four legacy inline seed titles are deactivated;
- custom/admin-created knowledge outside the manifest remains untouched.

PostgreSQL regression coverage was added.

### 6. Legacy plain-text reindex could destroy PDF provenance

`KnowledgeIndexService` could reindex PDF-backed documents from flattened `KnowledgeDocument.content`, removing section/page provenance.

Fix:
- the plain indexer refuses chunks marked `source_type=pdf`;
- `scripts/reindex_knowledge.py` routes canonical PDF documents through `PdfKnowledgeIngestionService`;
- direct `ingest_knowledge_pdfs.py --all --force` remains the canonical corpus refresh path.

PostgreSQL regression coverage was added.

### 7. PDF reading order

PyMuPDF block extraction now requests `sort=True` so visual reading order is used instead of PDF object insertion order.

Unit coverage includes out-of-order block insertion and malformed-PDF failure.

### 8. Evaluation evidence terminology

The section metric checks whether the expected section appears within the final top four chunks. It is therefore labeled **Section Recall@4**, not top-section accuracy.

The stored benchmark report also now states that its Git HEAD was recorded while the PDF implementation was still an uncommitted working tree. The report remains historical evidence and must be regenerated on the final QA head.

## Current runtime gate

GitHub-hosted Actions continues to exhibit the pre-existing external runner startup failure: the unit job completes with no assigned steps and the PostgreSQL job is skipped. This is not application failure evidence, but it also cannot be counted as a current-head pass.

Required before final Phase 2 signoff:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/unit
uv run pytest -m postgres -v
uv run pytest
uv run python scripts/ingest_knowledge_pdfs.py --all --dry-run
uv run python scripts/ingest_knowledge_pdfs.py --all
uv run python scripts/verify_rag.py
uv run python scripts/eval_rag.py
```

The live ingestion/evaluation commands must use the intended Supabase application DB only after deterministic unit/PostgreSQL gates pass. Destructive pytest cleanup remains restricted to the disposable local PostgreSQL database.

## Phase status

Until the current-head commands above execute successfully, Phase 2 remains **IN PROGRESS / STATUS NEEDS VERIFICATION**, even though the implementation and independent static QA hardening are complete.
