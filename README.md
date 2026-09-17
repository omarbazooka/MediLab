# MediLab AI

**Domain:** Diagnostic Laboratory AI Sales & Customer Service Agent  
**Current scope:** Phase 2 — Standalone Hybrid RAG Core
**Target deadline:** 20 September 2026

MediLab AI is a Flask-based diagnostic-laboratory customer-service/sales assessment project. Phase 2 establishes the modular, explainable, and deterministic hybrid RAG retrieval pipeline and managed knowledge lifecycle that later conversational LangGraph agents will use.

## Phase 2 status

Implemented and verified:

- Jina AI embeddings (`jina-embeddings-v3` @ 384 dimensions via Matryoshka truncation)
- Explicit task conditioning: `retrieval.passage` for document chunks, `retrieval.query` for search queries
- Deterministic paragraph-aware / word-bounded chunker supporting Arabic and English
- Atomic knowledge indexing lifecycle: `PENDING` -> `INDEXING` -> `READY` / `FAILED`
- PostgreSQL pgvector cosine distance (`<=>`) semantic search (top 8)
- PostgreSQL Full-Text Search against `search_vector` with `simple` dictionary (top 8)
- Reciprocal Rank Fusion (RRF with $k=60$) combining semantic and lexical scores
- Deterministic context-aware query rewrite baseline with Arabic/English pronoun ambiguity detection
- Signal-based retrieval grader: `GOOD`, `WEAK_RETRY`, `AMBIGUOUS_USER_QUERY`, `NO_KNOWLEDGE`
- Bounded retry: maximum of 1 alternate query retry on `WEAK_RETRY` (capped at 2 attempts)
- Context assembly: top 3–4 deduplicated chunks preserving document title, category, and chunk provenance
- Degraded mode: graceful single-arm fallback if semantic or lexical arm fails
- Full CRUD synchronization: Add, Update (version increment & chunk replacement), Delete, Deactivate
- Standalone RAG CLI utilities and evaluation runner measuring Recall@4 and MRR
- Zero LangGraph / Zero LLM generation (deferred to Phase 3)
- Zero database migrations required (`VECTOR(384)` schema preserved)

## Core Phase 1 models

- `TestCategory`, `LabTest`
- `Package`, `PackageTest`
- `Branch`, `AvailabilitySlot`
- `Customer`
- `Booking`, `BookingItem`, `HomeVisit`
- `KnowledgeDocument`, `KnowledgeChunk`
- `ConversationSession`, `ChatMessage`, `SearchSnapshot`

## Locked database decisions

Detailed decisions are recorded in `docs/decisions.md`.

- **Durable app DB:** Supabase-hosted PostgreSQL via `DATABASE_URL`
- **Disposable test DB:** Docker PostgreSQL + pgvector at `localhost:5432/medilab` via `TEST_DATABASE_URL`
- **Embedding schema contract:** `intfloat/multilingual-e5-small`, `VECTOR(384)`
- **HOME visit:** separate one-to-one `home_visits` table
- **Authoritative booking slot:** `Booking.availability_slot_id`
- **HOME/BRANCH slot uniqueness:** PostgreSQL partial unique indexes
- **FTS maintenance:** migration-managed trigger using `to_tsvector('simple', content)`
- **Customer resolution:** unique phone number

## Environment

Copy the example file and fill only local credentials/secrets:

```bash
cp .env.example .env
```

Required application variables:

```dotenv
MEDILAB_ENV=development
SECRET_KEY=<secure-local-secret>
DATABASE_URL=postgresql+psycopg://<supabase-user>:<password>@<host>:5432/postgres?sslmode=require
HOST=0.0.0.0
PORT=5000
LOG_LEVEL=INFO
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/medilab
```

Do not commit `.env`, Supabase passwords, service-role keys, or connection strings containing real credentials.

## Install

```bash
uv sync --frozen
```

## Disposable PostgreSQL / pgvector test database

Start only the disposable database service:

```bash
docker compose up -d db
docker compose ps
```

The Compose database is assessment/test infrastructure, not the durable application source of truth.

## Application database migration

For the real MediLab Supabase database:

```bash
uv run flask db current
uv run flask db upgrade
uv run flask db current
```

Current Phase 1 migration head:

```text
44cef7a277a7
```

### Clean migration rebuild — disposable DB only

Never run destructive downgrade/rebuild checks against Supabase.

PowerShell example:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab"
uv run flask db downgrade base
uv run flask db upgrade
Remove-Item Env:DATABASE_URL
```

A clean disposable rebuild has been verified through:

```text
base -> 7f6eb611e707 -> 44cef7a277a7
```

## Seed data

Run against the currently configured `DATABASE_URL`:

```bash
uv run python scripts/seed_db.py
```

The current fictional seed baseline is:

- 5 categories
- 11 lab tests
- 3 packages
- 4 Cairo branches
- 209 availability slots covering 15–25 September 2026
- 4 non-clinical knowledge documents with `index_status='PENDING'`

Running the seed twice is verified to keep the same entity counts without duplicate rows.

## Database verification

```bash
uv run python scripts/verify_db.py
```

The verification script checks the configured database for:

- PostgreSQL connectivity
- pgvector extension
- Alembic revision `44cef7a277a7`
- 15 core tables
- active snapshot-integrity trigger
- strengthened HOME booking constraint
- seed counts

## Phase 2 RAG Core commands

### 1. Live Jina Embeddings API verification
Verify live Jina AI Embeddings API call (English query & Arabic passage @ 384 dimensions):

```bash
uv run python scripts/verify_embeddings.py
```

### 2. Knowledge base indexing & synchronization
Index all active seeded knowledge documents:

```bash
uv run python scripts/reindex_knowledge.py --all
```

Index a specific document by ID or retry failed documents:

```bash
uv run python scripts/reindex_knowledge.py --document-id 1
uv run python scripts/reindex_knowledge.py --failed
```

### 3. Interactive RAG retrieval verification
Run benchmark queries (Arabic, English, paraphrased, no-answer) against the indexed knowledge base:

```bash
uv run python scripts/verify_rag.py
```

### 4. RAG evaluation benchmark
Run the evaluation suite across 15 bilingual cases to measure Recall@4, MRR, and latencies:

```bash
uv run python scripts/eval_rag.py
```
Outputs the detailed evaluation report to `docs/evaluation/phase2_rag_eval.md`.

## Business-service behavior

`BookingService` is deterministic and independently testable; it is not yet a LangGraph tool.

Creation behavior includes:

1. validate required input
2. resolve and lock the selected availability slot
3. validate visit type/branch/capacity
4. resolve/create customer
5. validate selected tests/packages and snapshot prices
6. reserve capacity transactionally
7. persist booking/items and optional `HomeVisit`
8. commit before returning the real booking reference

Booking references use:

```text
MLB-YYYYMMDD-XXXXXXXX
```

Cancellation locks the booking row before status evaluation and locks the authoritative slot before releasing capacity, preventing a concurrent double-decrement.

## Tests

Fast unit tests:

```bash
uv run pytest tests/unit
```

Verified result on Phase 2:

```text
96 passed in 1.81s
```

Real PostgreSQL integration tests:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab_test"
uv run pytest -m postgres -v
```

Verified result on disposable Docker PostgreSQL (zero skips):

```text
21 passed, 96 deselected in 3.30s
```

Full suite:

```bash
uv run pytest
```

Verified result:

```text
117 passed in 13.06s
```

## Phase 2 RAG Verification & Evaluation Scripts

Live Jina AI embeddings verification:

```bash
uv run python scripts/verify_embeddings.py
```

Full knowledge base reindexing against database:

```bash
uv run python scripts/reindex_knowledge.py --all
```

End-to-end RAG verification (hybrid retrieval, Arabic queries, CRUD synchronization, no-knowledge boundary):

```bash
uv run python scripts/verify_rag.py
```

Rigorous RAG evaluation across calibration and holdout sets:

```bash
uv run python scripts/eval_rag.py
```


Quality gates:

```bash
uv run ruff check .
uv run ruff format --check .
```

Verified result:

```text
All checks passed
51 files already formatted
```

## CI

`.github/workflows/ci.yml` contains two gates:

- unit tests + Ruff
- Docker/PostgreSQL/pgvector runtime + migrations + PostgreSQL integration tests

The Docker job explicitly injects an ephemeral local `DATABASE_URL` for the web container; it does not use Supabase in CI.

At the time of Phase 1 QA, GitHub-hosted Actions runs are failing before any step is assigned (`steps=[]`, Docker job skipped). This is treated as an external runner/startup issue, not as passing CI evidence. Local Docker/PostgreSQL and Supabase verification are the current runtime evidence.

## Healthcare boundary

MediLab AI is not clinical decision support. The project must not diagnose, interpret lab results clinically, prescribe/recommend medication, or recommend medically necessary tests from symptoms. Phase 1 seed knowledge is limited to approved customer-service/preparation/process information.

## Phase status semantics

- `IMPLEMENTED`: code exists
- `TESTED`: automated evidence passes
- `LIVE_VERIFIED`: real runtime/database evidence proves the behavior

Phase 1 should only be marked complete after independent QA accepts the current PR/commit.

## Next phase

Phase 2 implements RAG independently of LangGraph: managed knowledge lifecycle, chunking/embeddings, pgvector + PostgreSQL FTS hybrid retrieval, RRF, retrieval grading, bounded retry, and CRUD synchronization.
