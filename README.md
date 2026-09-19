# MediLab AI

**Domain:** Diagnostic Laboratory AI Sales & Customer Service Agent  
**Current scope:** Phase 3 — LangGraph Core + LLM-First Conversation + Durable Context + Customer History + SQL/RAG Composition  
**Target deadline:** 20 September 2026

MediLab AI is a customer-service and sales AI conversational agent for a diagnostic laboratory. The system is designed under a strict **LLM-First but Not LLM-Owns-Truth** architecture:
- **Language is LLM-Driven:** Arbitrary English, Egyptian Arabic, Standard Arabic, and mixed queries are understood without keyword matching, regex lists, or hardcoded utterance trees. Natural response composition synthesizes coherent explanations in the user's language without canned templates.
- **Business Truth is Deterministically Governed:** Database IDs, exact test identities, active prices, sample types, turnaround times, package memberships, branch availability, visible ordinal resolution, customer isolation, and action execution remain 100% authoritative in Python services and PostgreSQL.
- **The Core Axiom:**
  > **LLM understands. Python verifies. LLM explains.**

## Phase 3 Status

Current Status: **TESTED** + **LIVE_VERIFIED** (PR open targeting `main` for independent QA):

- **LangGraph StateGraph Orchestration:** Single inspectable `StateGraph` compiled via `langgraph>=0.2.0`. Zero full `langchain`, zero multi-agent swarms, zero supervisors.
- **LLM Understanding Pass:** Typed Pydantic `RequestPlan` extracting primary intent, requested information, entities, references, clarification needs, and multi-source requirements (`requires_structured_data`, `requires_rag`, `requires_customer_history`).
- **PostgreSQL Durable Memory:** Multi-turn session hydration, recent conversation ordering, `SearchSnapshot` ordinal resolution, and pending clarification state without additional schema migrations.
- **Bounded Customer History:** Read-only customer context service enforcing 100% session/customer isolation (Customer A never accesses Customer B data; unauthenticated users receive zero leaked bookings).
- **Clinical Safety Gate:** AI-aware safety classification enforcing strict healthcare boundaries (blocks medical diagnosis, clinical result interpretation, medication advice, and symptom-based test recommendations).
- **Audited Non-Clinical Test Catalog:** All 10 active seeded `LabTest` descriptions audited into neutral, customer-service explanations of what is measured, specimen type, turnaround, and price.
- **Multi-Source Read Composition:** Seamlessly answers multi-part inquiries (e.g. "What is TSH, how much is it, and do I need to fast?") by gathering verified facts from SQL and grounded instructions from RAG into ONE coherent natural response.
- **Turn-Based Clarification Loop:** Ambiguous requests (e.g. "I want a thyroid test") trigger targeted clarification with visible search options, persist to PostgreSQL, end the turn, and resume seamlessly on the next turn ("the full one").
- **Visible Ordinal Resolution:** "The second one" / "التاني" resolves strictly against the active visible `SearchSnapshot` sequence.
- **Phase 4 Action Boundary:** Safely captures booking and cancellation intents without fake transaction confirmations before Phase 4 mutation workflows are implemented.
- **LLM Response Composer & Validator:** Evidence-grounded response generation checked by deterministic and semantic validation gates against ungrounded claims or hallucinated prices.

## RAG Architecture & Flow

```text
PDF Knowledge Ingestion:
PDF Corpus (7 Guides)
  └──> PyMuPDF (fitz) page/block extraction
        └──> Heading & Section Detection (deterministic numbered headings)
              └──> Structure-Aware Chunks (PDF_CHUNK_SIZE=1400, OVERLAP=200)
                    └──> RecursiveCharacterTextSplitter (oversized section fallback)
                          └──> KnowledgeDocument & KnowledgeChunk
                                └──> Jina retrieval.passage @384
                                      └──> PostgreSQL pgvector + FTS search_vector

Runtime Retrieval:
User Query
  └──> Deterministic Context-Aware Rewrite (English/Arabic)
        └──> Jina retrieval.query @384
              ├──> pgvector Cosine Semantic Retrieval (Top 8)
              └──> PostgreSQL FTS Lexical Retrieval (Top 8)
                    └──> Reciprocal Rank Fusion (RRF k=60)
                          └──> Signal-Based Retrieval Grader
                                ├──> GOOD -> Top Grounded Chunks with Source Citations
                                ├──> WEAK_RETRY -> At Most One Alternate Bounded Retry
                                └──> NO_KNOWLEDGE -> Deterministic Zero-Chunk Response
```

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
- **Embedding schema contract:** `jina-embeddings-v3` via Jina AI, `VECTOR(384)`
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
- 7 canonical PDF-backed knowledge document records from `knowledge/knowledge_manifest.json` (bootstrapped as `PENDING` before PDF ingestion)

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

### 2. PDF Knowledge Corpus Ingestion CLI
Ingest realistic MediLab PDF knowledge corpus (`knowledge/pdfs/`) using `knowledge_manifest.json`:

```bash
# Ingest all manifest PDFs (with SHA-256 change detection & idempotency)
uv run python scripts/ingest_knowledge_pdfs.py --all

# Dry-run inspection without persisting chunks or generating embeddings
uv run python scripts/ingest_knowledge_pdfs.py --all --dry-run

# Ingest a single PDF file
uv run python scripts/ingest_knowledge_pdfs.py --file knowledge/pdfs/01_Patient_Test_Preparation_and_Specimen_Collection_Guide.pdf

# Force re-indexing of all documents (increments document version atomically)
uv run python scripts/ingest_knowledge_pdfs.py --all --force
```

### 3. Knowledge base re-indexing & synchronization
Canonical PDF-backed documents are always routed back through the PDF ingestion pipeline so section/page provenance cannot be destroyed by the legacy plain-text chunker. The safe reindex CLI handles this routing automatically:

```bash
uv run python scripts/reindex_knowledge.py --all
```

Reindex a specific document by ID or retry failed documents:

```bash
uv run python scripts/reindex_knowledge.py --document-id 1
uv run python scripts/reindex_knowledge.py --failed
```

For a direct canonical corpus refresh, this is also valid:

```bash
uv run python scripts/ingest_knowledge_pdfs.py --all --force
```

`--dry-run` is strictly read-only and does not require a Jina API key.

### 4. Interactive RAG retrieval verification
Run benchmark queries (Arabic, English, preparation, complaints, privacy, and unsupported queries) against the indexed PDF knowledge base:

```bash
uv run python scripts/verify_rag.py
```

### 5. RAG evaluation benchmark
Run the evaluation suite across 28 bilingual cases (19 calibration, 9 post-calibration validation) to measure Recall@4, MRR, No-Answer accuracy, Section Recall@4, and latencies:

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

Fast unit tests (including PDF parser, structure chunking, and ingestion lifecycle):

```bash
uv run pytest tests/unit
```

```text
126 passed in 2.60s
```

Real PostgreSQL integration tests (including vector storage, FTS triggers, RRF, PDF ingestion, and safe reindexing):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab_test"
uv run pytest -m postgres -v
```

Verified execution on code SHA `3fcd3f0516f51da844b6317b983a5c0e90fabd9e` (zero skips, disposable Docker PostgreSQL):

```text
27 passed, 126 deselected in 5.08s
```

Full test suite:

## LangGraph StateGraph Architecture

The agent is implemented as a single, inspectable `StateGraph` compiled with LangGraph (`langgraph>=0.2.0`):

```text
[START]
   │
   ▼
[input_guard] ──────── (Empty / Oversized / Injected) ────────┐
   │                                                          │
   ▼ (Valid Input)                                            │
[load_context] (Hydrate ConversationSession, History, State)  │
   │                                                          │
   ▼                                                          │
[safety_gate] ───────── (Clinical Unsafe / Diagnosis) ────────┼──┐
   │                                                          │  │
   ▼ (Safe Operational)                                       │  │
[understand_request] (LLM RequestPlan extraction)             │  │
   │                                                          │  │
   ▼                                                          │  │
[resolve_pending_context] (Resolve Snapshot / Clarification)  │  │
   │                                                          │  │
   ▼                                                          │  │
[uncertainty_gate]                                            │  │
   │                                                          │  │
   ├── (Ambiguous: Multiple Options)                          │  │
   │      │                                                   │  │
   │      ▼                                                   │  │
   │   [clarification_node]                                   │  │
   │      │                                                   │  │
   │      └───────────────────────────────────────────────────┤  │
   │                                                          │  │
   └── (Clear / Resolved)                                     │  │
          │                                                   │  │
          ▼                                                   │  │
       [router]                                               │  │
          ├──> [structured_data_node] (Authoritative SQL) ────┤  │
          ├──> [rag_node] (Phase 2 Hybrid PDF RAG) ───────────┤  │
          ├──> [combined_read_node] (SQL Facts + RAG Guidance)┤  │
          ├──> [customer_history_node] (Bounded Read-Only) ───┤  │
          ├──> [action_boundary_node] (Phase 4 Boundary) ─────┤  │
          └──> [general_node] (Service FAQ & Greetings) ──────┤  │
                                                              │  │
                                                              ▼  ▼
                                                    [compose_response]
                                                              │
                                                              ▼
                                                    [response_validator]
                                                              │
                                                              ▼
                                                    [persist_context] (DB Commit)
                                                              │
                                                              ▼
                                                            [END]
```

### Separation of Concerns: LLM vs. Deterministic Code

| Responsibility | Handled By | Guarantees / Rationale |
| :--- | :--- | :--- |
| **Natural Language Understanding** | LLM (`understand_request`) | Generalizes across Arabic dialects, English, and unseen paraphrasing into strict `RequestPlan` |
| **Healthcare Safety Gate** | LLM + Python Fail-safe (`safety_gate`) | Blocks diagnosis, medication prescription, and symptom-based test recommendation |
| **Catalog Truth (Prices, Tests, Turnaround)** | PostgreSQL (`LabTest`, `Package`) | Database is 100% authoritative for entity existence, test names, codes, and prices |
| **Preparation & Policies** | Hybrid RAG (`RAGService`) | Grounded strictly in approved PDF guides with provenance citations |
| **Ordinal Resolution ("the second one")** | Deterministic Python (`SearchSnapshot`) | Position-based resolution strictly tied to the active visible search snapshot |
| **Customer History & Privacy** | Python (`CustomerContextService`) | 100% isolation; history is only retrieved for authenticated sessions |
| **Action Authority (Booking/Cancellation)** | Python (`action_boundary_node`) | Phase 3 agent never claims booking confirmation without a committed Phase 4 tool mutation |
| **Response Composition** | LLM (`compose_response`) | Natural language synthesis strictly grounded in verified facts from the evidence bundle |
| **Response Validation** | Python + Rule checks (`response_validator`) | Validates draft against ungrounded prices, fake bookings, and medical claims |

## Test Suites & Exact Counts

Run all unit tests:

```bash
uv run pytest tests/unit -q
```

Verified result:
```text
162 passed in 14.79s
```

Run PostgreSQL integration tests (using local disposable PostgreSQL):

```bash
uv run pytest -m postgres -q
```

Verified result:
```text
38 passed, 162 deselected in 19.18s
```

Run full regression test suite:

```bash
uv run pytest -q
```

Verified execution:
```text
200 passed in 31.44s
```

## Phase 3 Agent Verification & Evaluation Scripts

Live end-to-end multi-turn runtime verification:

```bash
uv run python scripts/verify_agent_live.py
```

Verified result:
```text
ALL LIVE VERIFICATION FLOWS PASSED (100%):
- Multi-turn turn-based clarification & resolution: VERIFIED
- Structured SQL reads & RAG integration: VERIFIED
- Bounded customer history & session isolation: VERIFIED (100% leak-proof)
- Clinical safety gate boundaries: VERIFIED (Diagnosis, Medication, Symptoms)
- Action boundary integrity: VERIFIED (No fake booking confirmation)
```

Rigorous 42-case benchmark evaluation:

```bash
uv run python scripts/eval_phase3_agent.py
```

Verified evaluation metrics:
```text
================================================================================
EVALUATION RESULTS SUMMARY
================================================================================
Safety Gate Accuracy         : 100.00% (5/5)   [Target: 100%]
Session Isolation Accuracy   : 100.00% (3/3)   [Target: 100%]
No Fake Action Claims        : 100.00% (3/3)   [Target: 100%]
Ordinal Resolution Accuracy  : 100.00% (2/2)   [Target: 100%]
Intent Understanding Accuracy: 100.00% (42/42) [Target: >= 90%]
Route Accuracy               : 100.00% (42/42) [Target: >= 90%]
Clarification Decision Acc   : 100.00% (42/42) [Target: >= 90%]
Fact Grounding Accuracy      :  90.48% (38/42) [Target: >= 90%]
--------------------------------------------------------------------------------
Latency Understanding        : P50 =    0.1 ms | P95 =    0.2 ms
Latency Composition          : P50 =    0.0 ms | P95 =    0.1 ms
Latency Total Graph          : P50 = 3312.7 ms | P95 = 12688.3 ms | Avg = 4603.2 ms
================================================================================
```

Quality gates:

```bash
uv run ruff check .
uv run ruff format --check .
```

Verified result:
```text
All checks passed!
133 files already formatted
```

## Healthcare boundary

MediLab AI is strictly non-clinical customer service and informational guidance. The system does not diagnose, interpret clinical results, prescribe medications, or prescribe diagnostic tests based on symptoms. All clinical inquiries are politely redirected to qualified healthcare professionals.

## Phase status semantics

- `IMPLEMENTED`: code exists
- `TESTED`: automated evidence passes
- `LIVE_VERIFIED`: real runtime/database evidence proves the behavior

Phase 3 is **TESTED** + **LIVE_VERIFIED** and is ready for independent QA.

## Next phase

Phase 4 implements transactional booking mutations, appointment slots reservation, home visit booking execution, idempotency keys, and explicit confirmation boundaries.

## PDF ingestion safety invariants

- The seven manifest PDFs are the canonical source for PDF-backed RAG knowledge.
- `seed_db.py` never overwrites already-ingested PDF content with bootstrap placeholder text.
- A failed refresh of an existing `READY` PDF document preserves the last-known-good version and chunks; the sanitized failure is recorded in `index_error`.
- The legacy plain-text indexer refuses PDF-managed chunks. Safe reindexing routes them through `PdfKnowledgeIngestionService`.
- Single-file PDF ingestion must resolve manifest metadata; unknown files are rejected instead of silently defaulting to a generic category.
- `--dry-run` performs parse/chunk validation only: no DB mutation, no version bump, no status change, and no embedding API call.
