# MediLab AI

**Domain:** Diagnostic Laboratory AI Sales & Customer Service Agent  
**Current scope:** Phase 1 — ORM, Migrations & Seed Data  
**Target deadline:** 20 September 2026

MediLab AI is a Flask-based diagnostic-laboratory customer-service/sales assessment project. Phase 1 establishes the deterministic PostgreSQL persistence and business-service foundation that later RAG, LangGraph, customer UI, and admin phases will use.

## Phase 1 status

Implemented and locally/live verified on the Phase 1 branch:

- 15 SQLAlchemy 2.x domain models
- Supabase-hosted PostgreSQL as the durable application database
- disposable Docker PostgreSQL 16 + pgvector for migration/integration testing
- Alembic migrations through revision `44cef7a277a7`
- pgvector `VECTOR(384)` schema for `intfloat/multilingual-e5-small`
- PostgreSQL FTS `TSVECTOR` maintenance trigger + GIN index
- deterministic test/package/branch/availability services
- transactional branch and HOME booking service
- slot row locking, idempotency, controlled rollback, cancellation locking
- visible `SearchSnapshot` persistence with cross-session active-snapshot protection
- deterministic, rerunnable fictional seed data

Not implemented yet: RAG runtime/retrieval, LangGraph orchestration, customer chat UI, admin dashboard, and Meta Messenger.

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

Verified result on the Phase 1 QA commit:

```text
43 passed
```

Real PostgreSQL integration tests:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab"
uv run pytest -m postgres -v
```

Verified result:

```text
15 passed, 43 deselected
```

Full suite:

```bash
uv run pytest
```

Verified result:

```text
58 passed
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
