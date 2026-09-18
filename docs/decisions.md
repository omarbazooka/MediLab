# MediLab AI — Architecture Decisions Log

This document records authoritative technical decisions that are locked for the current implementation.

---

## Decision 1: Durable application DB vs. disposable test DB

- **Status:** LOCKED
- **Durable application database:** Supabase-hosted PostgreSQL via `DATABASE_URL`.
- **Persistence path:** `Flask -> Services -> Repositories -> SQLAlchemy -> PostgreSQL`.
- **Disposable test database:** Docker PostgreSQL 16 + pgvector using `pgvector/pgvector:0.8.6-pg16-bookworm`.
- **Current local test endpoint:** `localhost:5432/medilab` via `TEST_DATABASE_URL`.
- **Safety rule:** integration tests and destructive migration rebuild checks must never target the Supabase application database. The pytest guard rejects Supabase test URLs and application/test URL collisions.

Supabase is used as hosted PostgreSQL only; Phase 1 does not add Supabase-specific application SDKs or ORM abstractions.

---

## Decision 2: Embedding model and vector dimension

- **Status:** LOCKED (UPDATED FOR PHASE 2)
- **Previous Phase 1 Storage Assumption:** `intfloat/multilingual-e5-small` (local HF runtime assumption).
- **Phase 2 Runtime Decision:** `jina-embeddings-v3` via Jina AI Embeddings API.
- **Task Types:** `retrieval.passage` for document chunks, `retrieval.query` for search queries.
- **Vector Dimension:** `384` (enforced via Jina v3 Matryoshka dimension truncation).
- **Schema Mapping:** `KnowledgeChunk.embedding -> VECTOR(384)`.
- **Date Updated:** 2026-09-17.
- **Rationale:**
  1. Superior multilingual capability across Modern Standard Arabic and colloquial Egyptian Arabic healthcare queries.
  2. Asymmetric task conditioning (`retrieval.query` vs `retrieval.passage`) optimizes query-document alignment without synthetic fine-tuning.
  3. Support for Matryoshka dimension truncation enables restricting outputs to 384 dimensions, exactly matching the Phase 1 schema invariant.
  4. Lightweight API integration via `httpx` avoids heavy PyTorch / transformers dependencies in production.
- **Schema Migration Status:** NO SCHEMA MIGRATION REQUIRED. `VECTOR(384)` remains identical.
- **Affected Files:** `app/config.py`, `app/rag/embeddings.py`, `app/rag/indexing.py`, `scripts/verify_embeddings.py`.

---

## Decision 3: Separate one-to-one HomeVisit

- **Status:** LOCKED
- **Decision:** HOME-only address/process fields live in a separate `home_visits` table with a unique FK to `bookings.id`.
- **Status domain:** `REQUESTED`, `SCHEDULED`, `DISPATCHED`, `SAMPLE_COLLECTED`, `CANCELLED`.

This keeps branch bookings free from HOME-only nullable fields and gives the later dashboard a clear domain boundary.

---

## Decision 4: Authoritative availability-slot reference

- **Status:** LOCKED
- **Decision:** `Booking.availability_slot_id` references the exact reserved `AvailabilitySlot` with `ON DELETE RESTRICT`.
- **Historical snapshots:** `scheduled_date`, `scheduled_time`, `branch_id`, and `visit_type` remain on the Booking record as booking-time facts.

Cancellation uses the authoritative slot reference to release the correct capacity.

---

## Decision 5: AvailabilitySlot partial uniqueness

- **Status:** LOCKED
- **BRANCH slots:** unique `(branch_id, date, time)` where `visit_type = 'BRANCH'`.
- **HOME pool slots:** unique `(date, time)` where `visit_type = 'HOME' AND branch_id IS NULL`.

This avoids PostgreSQL NULL semantics allowing duplicate HOME pool slots.

---

## Decision 6: PostgreSQL FTS maintenance

- **Status:** LOCKED
- **Storage:** `KnowledgeChunk.search_vector` is PostgreSQL `TSVECTOR`.
- **Maintenance:** migration-managed trigger updates it from `content` on INSERT/UPDATE.
- **Configuration:** `simple` text-search dictionary for the current Arabic/English MVP.
- **Index:** GIN on `search_vector`.

Phase 2 owns lexical retrieval/ranking/fusion; Phase 1 only guarantees correct storage/index maintenance.

---

## Decision 7: Customer phone uniqueness

- **Status:** LOCKED
- **Decision:** `Customer.phone` is unique and indexed for deterministic customer resolution in the MVP.
- **Concurrency:** repository logic uses a nested transaction/savepoint and re-query to resolve concurrent create races without returning a duplicate customer row.

---

## Decision 8: Foreign-key cascade policy

- **Status:** LOCKED
- **Rule:** no blanket cascade deletion.
- **Child-owned cascades:** `KnowledgeDocument -> KnowledgeChunk`, `ConversationSession -> ChatMessage/SearchSnapshot`, `Booking -> BookingItem/HomeVisit`, `Package -> PackageTest`.
- **Historical/business references:** customer, branch, authoritative slot, lab-test/package booking references use `RESTRICT` or `SET NULL` where appropriate.

---

## Decision 9: ConversationSession / SearchSnapshot circular FK and ownership

- **Status:** LOCKED
- `SearchSnapshot.session_id -> ConversationSession.session_id` stores ownership.
- `ConversationSession.active_snapshot_id -> SearchSnapshot.id` stores the current visible snapshot.
- The circular FK is created after both tables exist; ORM wiring uses `use_alter=True` / `post_update=True` where required.
- Cross-session active-snapshot assignment is rejected at repository/model level and by the PostgreSQL trigger `trg_conversation_sessions_snapshot_integrity`.

Visible ordinal references in later phases must resolve against exactly this active persisted snapshot.

---

## Decision 10: Booking concurrency and idempotency

- **Status:** LOCKED
- Slot reservation locks the selected `AvailabilitySlot` row before capacity mutation.
- `Booking.idempotency_key` is unique and concurrency recovery returns the existing booking instead of creating a duplicate.
- Cancellation locks the Booking row before status evaluation, then locks/releases the authoritative slot exactly once.
- Booking references use `MLB-YYYYMMDD-XXXXXXXX` with bounded collision retry and database uniqueness as the final guard.

---

## Decision 11: Phase 1 migration head

- **Status:** LOCKED FOR CURRENT PHASE 1 QA
- Initial schema: `7f6eb611e707`.
# MediLab AI — Architecture Decisions Log

This document records authoritative technical decisions that are locked for the current implementation.

---

## Decision 1: Durable application DB vs. disposable test DB

- **Status:** LOCKED
- **Durable application database:** Supabase-hosted PostgreSQL via `DATABASE_URL`.
- **Persistence path:** `Flask -> Services -> Repositories -> SQLAlchemy -> PostgreSQL`.
- **Disposable test database:** Docker PostgreSQL 16 + pgvector using `pgvector/pgvector:0.8.6-pg16-bookworm`.
- **Current local test endpoint:** `localhost:5432/medilab` via `TEST_DATABASE_URL`.
- **Safety rule:** integration tests and destructive migration rebuild checks must never target the Supabase application database. The pytest guard rejects Supabase test URLs and application/test URL collisions.

Supabase is used as hosted PostgreSQL only; Phase 1 does not add Supabase-specific application SDKs or ORM abstractions.

---

## Decision 2: Embedding model and vector dimension

- **Status:** LOCKED (UPDATED FOR PHASE 2)
- **Previous Phase 1 Storage Assumption:** `intfloat/multilingual-e5-small` (local HF runtime assumption).
- **Phase 2 Runtime Decision:** `jina-embeddings-v3` via Jina AI Embeddings API.
- **Task Types:** `retrieval.passage` for document chunks, `retrieval.query` for search queries.
- **Vector Dimension:** `384` (enforced via Jina v3 Matryoshka dimension truncation).
- **Schema Mapping:** `KnowledgeChunk.embedding -> VECTOR(384)`.
- **Date Updated:** 2026-09-17.
- **Rationale:**
  1. Superior multilingual capability across Modern Standard Arabic and colloquial Egyptian Arabic healthcare queries.
  2. Asymmetric task conditioning (`retrieval.query` vs `retrieval.passage`) optimizes query-document alignment without synthetic fine-tuning.
  3. Support for Matryoshka dimension truncation enables restricting outputs to 384 dimensions, exactly matching the Phase 1 schema invariant.
  4. Lightweight API integration via `httpx` avoids heavy PyTorch / transformers dependencies in production.
- **Schema Migration Status:** NO SCHEMA MIGRATION REQUIRED. `VECTOR(384)` remains identical.
- **Affected Files:** `app/config.py`, `app/rag/embeddings.py`, `app/rag/indexing.py`, `scripts/verify_embeddings.py`.

---

## Decision 3: Separate one-to-one HomeVisit

- **Status:** LOCKED
- **Decision:** HOME-only address/process fields live in a separate `home_visits` table with a unique FK to `bookings.id`.
- **Status domain:** `REQUESTED`, `SCHEDULED`, `DISPATCHED`, `SAMPLE_COLLECTED`, `CANCELLED`.

This keeps branch bookings free from HOME-only nullable fields and gives the later dashboard a clear domain boundary.

---

## Decision 4: Authoritative availability-slot reference

- **Status:** LOCKED
- **Decision:** `Booking.availability_slot_id` references the exact reserved `AvailabilitySlot` with `ON DELETE RESTRICT`.
- **Historical snapshots:** `scheduled_date`, `scheduled_time`, `branch_id`, and `visit_type` remain on the Booking record as booking-time facts.

Cancellation uses the authoritative slot reference to release the correct capacity.

---

## Decision 5: AvailabilitySlot partial uniqueness

- **Status:** LOCKED
- **BRANCH slots:** unique `(branch_id, date, time)` where `visit_type = 'BRANCH'`.
- **HOME pool slots:** unique `(date, time)` where `visit_type = 'HOME' AND branch_id IS NULL`.

This avoids PostgreSQL NULL semantics allowing duplicate HOME pool slots.

---

## Decision 6: PostgreSQL FTS maintenance

- **Status:** LOCKED
- **Storage:** `KnowledgeChunk.search_vector` is PostgreSQL `TSVECTOR`.
- **Maintenance:** migration-managed trigger updates it from `content` on INSERT/UPDATE.
- **Configuration:** `simple` text-search dictionary for the current Arabic/English MVP.
- **Index:** GIN on `search_vector`.

Phase 2 owns lexical retrieval/ranking/fusion; Phase 1 only guarantees correct storage/index maintenance.

---

## Decision 7: Customer phone uniqueness

- **Status:** LOCKED
- **Decision:** `Customer.phone` is unique and indexed for deterministic customer resolution in the MVP.
- **Concurrency:** repository logic uses a nested transaction/savepoint and re-query to resolve concurrent create races without returning a duplicate customer row.

---

## Decision 8: Foreign-key cascade policy

- **Status:** LOCKED
- **Rule:** no blanket cascade deletion.
- **Child-owned cascades:** `KnowledgeDocument -> KnowledgeChunk`, `ConversationSession -> ChatMessage/SearchSnapshot`, `Booking -> BookingItem/HomeVisit`, `Package -> PackageTest`.
- **Historical/business references:** customer, branch, authoritative slot, lab-test/package booking references use `RESTRICT` or `SET NULL` where appropriate.

---

## Decision 9: ConversationSession / SearchSnapshot circular FK and ownership

- **Status:** LOCKED
- `SearchSnapshot.session_id -> ConversationSession.session_id` stores ownership.
- `ConversationSession.active_snapshot_id -> SearchSnapshot.id` stores the current visible snapshot.
- The circular FK is created after both tables exist; ORM wiring uses `use_alter=True` / `post_update=True` where required.
- Cross-session active-snapshot assignment is rejected at repository/model level and by the PostgreSQL trigger `trg_conversation_sessions_snapshot_integrity`.

Visible ordinal references in later phases must resolve against exactly this active persisted snapshot.

---

## Decision 10: Booking concurrency and idempotency

- **Status:** LOCKED
- Slot reservation locks the selected `AvailabilitySlot` row before capacity mutation.
- `Booking.idempotency_key` is unique and concurrency recovery returns the existing booking instead of creating a duplicate.
- Cancellation locks the Booking row before status evaluation, then locks/releases the authoritative slot exactly once.
- Booking references use `MLB-YYYYMMDD-XXXXXXXX` with bounded collision retry and database uniqueness as the final guard.

---

## Decision 11: Phase 1 migration head

- **Status:** LOCKED FOR CURRENT PHASE 1 QA
- Initial schema: `7f6eb611e707`.
- Forward QA hardening migration: `44cef7a277a7`.

All future schema changes must be additive Alembic migrations; do not rewrite already-applied Supabase migration history.

---

## Decision 12: Phase 2 Hybrid RAG Retrieval Architecture

- **Status:** LOCKED FOR PHASE 2
- **Semantic Retrieval:** PostgreSQL pgvector cosine distance (`<=>`), returning top-8 candidates from active, `READY` documents using 384-dimensional `jina-embeddings-v3` (or config-selected provider).
- **Lexical Retrieval:** PostgreSQL Full-Text Search against `KnowledgeChunk.search_vector` using `to_tsquery('simple', ...)` with `ts_rank_cd`, returning top-8 candidates from active, `READY` documents.
- **Score Fusion:** Reciprocal Rank Fusion (RRF) with constant $k=60$. Deduplicates by `chunk_id` and reinforces dual-arm hits.
- **Embedding Provider Factory:** Production wiring uses `get_embedding_provider(config=None)`. Reads `EMBEDDING_PROVIDER`, `JINA_API_KEY`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSION`. Missing required Jina API key or misconfigured dimension raises an explicit `EmbeddingConfigError` rather than silently degrading.
- **Query Rewrite Baseline:** Deterministic context-aware query rewrite handling English and Arabic anaphoric/ambiguous pronouns without requiring general LLM generation in Phase 2. Ambiguous queries without trusted grounding return `AMBIGUOUS_USER_QUERY` (never guess).
- **Retrieval Grading:** Observable signal-based evaluation (dual-arm agreement, cosine distance floors, lexical evidence).
- **Bounded Retry:** Maximum of 1 retry on `WEAK_RETRY` using alternate normalized/entity-grounded query terms; strictly capped at 2 attempts total.
- **Final Context Assembly & Budget:** Top 3–4 deduplicated chunks (default 4) preserving title, category, version, and chunk provenance. Enforces deterministic word budget (600 words) and character budget (3500 characters) while preserving whole, complete chunk texts (never truncating or slicing sentences).
- **Evaluation Integrity & Latency Accounting:** Evaluation suite currently uses 28 bilingual cases split into 19 calibration and 9 post-calibration validation cases. The validation split is explicitly NOT described as an independent holdout because some cases were inspected during QA hardening. Metrics include Recall@4, MRR, deterministic no-answer correctness, section-title retrieval accuracy, retry rate, and latency distribution (Average, P50, P95, Min, Max). Correctness failures return non-zero; the internal <500ms P95 latency target remains a measured, non-blocking engineering target.
- **Reranker:** DEFERRED / CORE ENHANCEMENT. Learned neural rerankers (Cohere, Jina Reranker) are deferred to post-Phase 2 optimization to preserve baseline predictability and deadline safety.

---

## Decision 13: Structure-Aware PDF Ingestion, PyMuPDF, and LangChain Splitter Boundary

- **Status:** LOCKED FOR PHASE 2 CORE ENHANCEMENT
- **Core Document Parser:** PyMuPDF (`fitz` / `pymupdf`). Extracts page numbers, block order, bounding boxes, running headers, and raw text without heavyweight OCR or external SaaS dependencies.
- **Section & Heading Detection:** Deterministic structural parser (`app/rag/parsers/pdf.py`). Detects numbered section headings (`1. Purpose`, `2. Fasting...`) and standard document metadata blocks (`MEDILAB`, category, document notes). Preserves clean section boundaries so unrelated sections are never blended into a single chunk.
- **LangChain Dependency Boundary:** Uses ONLY `langchain-text-splitters` (`RecursiveCharacterTextSplitter`). The full `langchain` and `langchain-community` packages are explicitly banned. `RecursiveCharacterTextSplitter` is employed strictly as a bounded fallback splitter INSIDE oversized detected sections. The MediLab RAG pipeline is a custom Python retrieval pipeline, NOT built with LangChain.
- **Chunk Parameters (Engineering Defaults):**
  - `PDF_CHUNK_SIZE = 1400` characters (target: ~1200–1800 chars)
  - `PDF_CHUNK_OVERLAP = 200` characters (target: ~150–250 chars)
- **Metadata & Provenance Contract:** Rich PDF source provenance is persisted inside the existing `KnowledgeChunk.metadata_` JSON column without schema migrations:
  - `source_file`: canonical PDF filename (e.g., `01_Patient_Test_Preparation_and_Specimen_Collection_Guide.pdf`)
  - `source_type`: `"pdf"`
  - `section_title`: detected section title (e.g., `"3. Fasting and Hydration"`)
  - `section_number`: detected section number (e.g., `"3"`)
  - `page_start`: 1-indexed start page
  - `page_end`: 1-indexed end page
  - `content_hash`: SHA-256 hash of the source PDF for change detection and idempotency
  - `document_version`: integer version tracking for stale-chunk protection
- **Document Identity:** One PDF = One logical `KnowledgeDocument`. Manifest-driven ingestion (`knowledge/knowledge_manifest.json`) defines title, category, version, and SQL/RAG boundary.
- **Data Boundary & Content Integrity:** Operational and policy guidance belongs to RAG (fasting instructions, service policies, specimen recollection procedures, privacy rules, complaint escalation). Business facts remain in SQL truth (live test prices, package prices, branch availability slots, booking state, customer records). Specific test turnaround times (e.g., Vitamin D = 48 Hours) remain in SQL LabTest data, while RAG defines general turnaround calculation and delay policies.
- **CLI & Automation:** `scripts/ingest_knowledge_pdfs.py` supports `--all`, `--file <path>`, `--dry-run`, and `--force`, enforcing safe database URL masking, zero API key leakage, manifest-safe single-file ingestion, read-only dry-run behavior, atomic replacement, and exit-code propagation.
- **Canonical Ownership:** The repository PDF corpus is the source of truth for the seven operational knowledge documents. `seed_db.py` may create/bootstrap document records and synchronize stable manifest metadata, but it must never overwrite parsed PDF content after ingestion. Generic plain-text indexing is forbidden for PDF-managed chunks; safe reindex commands route canonical PDFs back through `PdfKnowledgeIngestionService`.
- **Failed Refresh Safety:** Existing `READY` PDF documents remain retrievable until replacement parsing/chunking/embeddings are successfully prepared. A failed refresh preserves the last-known-good version/chunks and records a sanitized `index_error` rather than taking a healthy index offline.

