# MediLab AI

**Domain:** Diagnostic Laboratory AI Sales & Customer Service Agent  
**Current scope:** Phase 1 — Persistence, Business Models, Migrations & Seed Data  
**Target Deadline:** 20 September 2026

MediLab AI is a diagnostic laboratory AI customer service and sales agent built with Flask, SQLAlchemy 2.x, PostgreSQL 17 (Supabase durable storage) + Docker PostgreSQL 16 (disposable test database), and pgvector.

---

## Phase 1 Scope & Deliverables

Phase 1 establishes the persistent business foundation for the upcoming RAG, conversational, and booking workflows:

1. **15 Core SQLAlchemy 2.x Domain Models:**
   - Catalog: `TestCategory`, `LabTest`, `Package`, `PackageTest`
   - Facilities & Scheduling: `Branch`, `AvailabilitySlot`
   - Customer & Booking: `Customer`, `Booking`, `BookingItem`, `HomeVisit`
   - Knowledge & RAG: `KnowledgeDocument`, `KnowledgeChunk`
   - Conversation State & Snapshots: `ConversationSession`, `ChatMessage`, `SearchSnapshot`

2. **Alembic Database Migrations:**
   - Authoritative, reversible initial migration with pgvector extension creation.
   - Clean circular FK resolution (`ConversationSession.active_snapshot_id` <-> `SearchSnapshot.session_id`) using `use_alter=True` and post-creation foreign key assignment.
   - Automated PostgreSQL database trigger maintaining `KnowledgeChunk.search_vector` via `to_tsvector('simple', content)`.

3. **Authoritative Slot Reservation & Scheduling:**
   - Distinct partial uniqueness:
     - `BRANCH`: unique on `(branch_id, date, time)` where `visit_type = 'BRANCH'`
     - `HOME`: unique on `(date, time)` where `visit_type = 'HOME' AND branch_id IS NULL`
   - `Booking.availability_slot_id` is the authoritative source for the reserved slot; `scheduled_date`, `scheduled_time`, `branch_id`, and `visit_type` are retained as immutable snapshots.

4. **1-to-1 HomeVisit Workflow:**
   - Separate `home_visits` table with bounded status enum (`REQUESTED`, `SCHEDULED`, `DISPATCHED`, `SAMPLE_COLLECTED`, `CANCELLED`).

5. **Customer Resolution:**
   - `Customer.phone` is constrained as `unique=True, index=True` for unambiguous deterministic customer resolution.

6. **Transactional Booking Service:**
   - Atomic slot capacity locking with `with_for_update`.
   - Idempotency key protection preventing duplicate bookings or overbooking.
   - Immediate rollback on failure leaving zero partial state.
   - Canonical booking reference generation: `MLB-YYYYMMDD-XXXX`.

7. **Deterministic Seed Data (`scripts/seed_db.py`):**
   - 5 Categories (`Hematology`, `Clinical Chemistry`, `Endocrinology & Hormones`, `Diabetes Care`, `General Wellness`)
   - 11 Lab Tests (including 1 inactive legacy audit test)
   - 3 Packages (`Comprehensive Health Checkup`, `Diabetes Monitoring`, `Vitality & Wellness`)
   - 4 Cairo Branches (`Nasr City`, `Maadi`, `Dokki`, `New Cairo`) with bilingual opening hours
   - 95 Branch and Home Availability Slots
   - 4 Authoritative Knowledge Documents (`index_status='PENDING'`)
   - 100% idempotent via natural keys.

---

## Architecture Decisions (Locked)

Detailed in `docs/decisions.md`:

| Decision | Specification |
|---|---|
| **Durable Application DB** | Supabase-hosted PostgreSQL 17 (`aws-1-eu-west-1.pooler.supabase.com:5432/postgres`) via `DATABASE_URL` |
| **Disposable Test DB** | Docker Compose PostgreSQL 16 + pgvector (`localhost:5432/medilab_test` or `5433`) via `TEST_DATABASE_URL` |
| **Test Safety Guard** | Hard-coded runtime guard blocks integration tests if `TEST_DATABASE_URL == DATABASE_URL` or points to Supabase |
| **Embeddings** | `intfloat/multilingual-e5-small` / `VECTOR(384)` |
| **FTS Configuration** | Database trigger maintains `search_vector` with `simple` dictionary and GIN index |
| **FK Cascades** | Strict child-owned cascades only (`Doc -> Chunk`, `Session -> Message/Snapshot`, `Booking -> Item/HomeVisit`, `Package -> PackageTest`). Business references enforce `RESTRICT` |

---

## Directory Layout

```text
medilab-ai/
├── app/
│   ├── blueprints/
│   │   ├── __init__.py
│   │   └── health/
│   ├── models/                  # 15 SQLAlchemy 2.x domain models
│   │   ├── __init__.py
│   │   ├── base.py              # TimestampMixin, JSON_VARIANT, TSVECTOR_VARIANT
│   │   ├── booking.py           # Booking, BookingItem
│   │   ├── branch.py            # Branch, AvailabilitySlot
│   │   ├── conversation.py      # ConversationSession, ChatMessage
│   │   ├── customer.py          # Customer
│   │   ├── home_visit.py        # HomeVisit (1:1 with Booking)
│   │   ├── knowledge.py         # KnowledgeDocument, KnowledgeChunk (VECTOR(384))
│   │   ├── package.py           # Package, PackageTest
│   │   ├── snapshot.py          # SearchSnapshot
│   │   └── test.py              # TestCategory, LabTest
│   ├── repositories/            # Data access layers
│   │   ├── booking_repository.py
│   │   ├── branch_repository.py
│   │   ├── customer_repository.py
│   │   ├── package_repository.py
│   │   └── test_repository.py
│   ├── services/                # Business logic services
│   │   ├── booking_service.py   # Atomic slot locking, idempotency, cancellation
│   │   ├── branch_service.py
│   │   ├── package_service.py
│   │   └── test_service.py
│   ├── config.py
│   ├── errors.py
│   ├── extensions.py
│   ├── logging.py
│   └── request_ids.py
├── docs/
│   └── decisions.md             # Locked architectural decisions log
├── migrations/                  # Alembic migration revisions
│   └── versions/
│       └── 7f6eb611e707_initial_phase1_schema.py
├── scripts/
│   ├── seed_db.py               # Idempotent catalog, branch, and policy seed script
│   └── verify_db.py             # PostgreSQL connection and pgvector verification
├── tests/
│   ├── conftest.py              # App fixtures & database safety isolation guard
│   ├── unit/                    # Fast isolated unit test suite (31 tests)
│   └── integration/             # Real PostgreSQL integration suite (10 tests)
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

---

## Setup & Running

### 1. Environment Setup

```bash
git clone https://github.com/omarbazooka/MediLab.git
cd MediLab
git checkout feat/phase1-database-foundation
cp .env.example .env
uv sync
```

Set credentials in `.env`:
- `DATABASE_URL`: Supabase PostgreSQL URL
- `TEST_DATABASE_URL`: Local disposable Docker PostgreSQL URL (`postgresql+psycopg://postgres:postgres@localhost:5432/medilab_test`)

### 2. Database Migrations

Apply migration to Supabase application database:
```bash
uv run flask db upgrade
```

Verify migration status:
```bash
uv run flask db current
```

Test clean migration rebuild on disposable test DB:
```bash
$env:FLASK_APP="app:create_app('testing', test_config={'SQLALCHEMY_DATABASE_URI': '$env:TEST_DATABASE_URL'})"
uv run flask db downgrade base
uv run flask db upgrade
```

### 3. Database Seeding

Run idempotent catalog seed:
```bash
uv run python scripts/seed_db.py
```

Verify connection and pgvector extension:
```bash
uv run python scripts/verify_db.py
```

---

## Tests and Quality Gates

Fast unit test suite (runs in memory without Docker/PostgreSQL):
```bash
uv run pytest tests/unit
```

PostgreSQL integration test suite (targets disposable Docker DB only):
```bash
uv run pytest tests/integration
```

Run entire 41-test suite:
```bash
uv run pytest
```

Code formatting and linting:
```bash
uv run ruff check .
uv run ruff format --check .
```

---

## QA Handoff Status

- **Branch:** `feat/phase1-database-foundation`
- **Pull Request:** Open against `main` (not merged, pending independent QA review)
- **Unit Tests:** 31 passed
- **Integration Tests:** 10 passed (targeting disposable Docker PostgreSQL)
- **Supabase Durable DB:** Migrated and seeded idempotently
- **Zero regressions** against Phase 0 baseline
