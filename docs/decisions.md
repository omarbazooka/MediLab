# MediLab AI — Architecture Decisions Log

This document records the authoritative, locked technical decisions for MediLab AI.

---

## Decision 1: Durable Application Database vs. Disposable Test Database
- **Status:** LOCKED
- **Decision:**
  - **Durable Application Database:** Hosted **Supabase PostgreSQL 17** via `DATABASE_URL`. Supabase is utilized strictly as hosted PostgreSQL; no Supabase-specific client SDKs or proprietary ORM extensions are introduced. Standard persistence flows: `Flask -> Services -> Repositories -> SQLAlchemy -> PostgreSQL`.
  - **Disposable Test Database:** Containerized **PostgreSQL 16 + pgvector** (`pgvector/pgvector:0.8.6-pg16-bookworm`) via `TEST_DATABASE_URL` running on port 5433 (or dedicated local test container).
  - **Safety Rule:** Integration tests, migration rebuilds, and destructive fixtures MUST strictly target `TEST_DATABASE_URL`. Destructive operations are actively guarded and will fail immediately if `TEST_DATABASE_URL == DATABASE_URL`.

---

## Decision 2: Embedding Model and Vector Dimension
- **Status:** LOCKED
- **Model:** `intfloat/multilingual-e5-small`
- **Vector Dimension:** `384`
- **Schema Mapping:** `KnowledgeChunk.embedding` is explicitly typed as `VECTOR(384)` using `pgvector.sqlalchemy.Vector(384)`.
- **Rationale:** Supports bilingual Arabic and English queries efficiently with low storage and memory overhead compared to larger models.

---

## Decision 3: Separate 1-to-1 HomeVisit Table
- **Status:** LOCKED
- **Decision:** Home visit requests are persisted in a dedicated `home_visits` table with a unique foreign key to `bookings.id` (1-to-1 relationship).
- **Rationale:**
  - Prevents nullable address/area fields on standard branch bookings.
  - Clear administrative distinction between clinical branch visits and home sample collections.
  - Bounded status workflow: `REQUESTED`, `SCHEDULED`, `DISPATCHED`, `SAMPLE_COLLECTED`, `CANCELLED`.

---

## Decision 4: Authoritative Availability Slot Reference
- **Status:** LOCKED
- **Decision:** `Booking.availability_slot_id` (`ForeignKey("availability_slots.id", ondelete="RESTRICT")`) is the authoritative source for the reserved slot.
- **Audit Snapshots:** `Booking.scheduled_date`, `Booking.scheduled_time`, `Booking.branch_id`, and `Booking.visit_type` are retained directly on `Booking` as immutable audit snapshots reflecting the state when booked.

---

## Decision 5: AvailabilitySlot Partial Uniqueness Constraints
- **Status:** LOCKED
- **Decision:**
  - `BRANCH` slots enforce uniqueness across `(branch_id, date, time)` where `visit_type = 'BRANCH'`.
  - `HOME` slots enforce pool uniqueness across `(date, time)` where `visit_type = 'HOME' AND branch_id IS NULL`.
- **Rationale:** PostgreSQL partial unique indexes avoid ambiguity around SQL NULL semantics in multi-column unique constraints.

---

## Decision 6: PostgreSQL Full-Text Search (FTS) Maintenance Strategy
- **Status:** LOCKED
- **Decision:** `KnowledgeChunk.search_vector` is maintained automatically via a migration-managed PostgreSQL trigger using the `simple` text search dictionary:
  ```sql
  NEW.search_vector := to_tsvector('simple', coalesce(NEW.content, ''));
  ```
  Indexed with a GIN index:
  ```sql
  CREATE INDEX ix_knowledge_chunks_search_vector ON knowledge_chunks USING gin (search_vector);
  ```
- **Rationale:** The `simple` dictionary provides unbiased tokenization for bilingual Arabic and English healthcare content without English-only stemming distortions. The database trigger guarantees that any insert or update to `content` immediately updates `search_vector`.

---

## Decision 7: Customer Resolution & Phone Uniqueness
- **Status:** LOCKED
- **Decision:** `Customer.phone` is constrained as `unique=True, index=True`.
- **Rationale:** Ensures deterministic, unambiguous `get_or_create` customer resolution across multi-turn booking and consultation flows.

---

## Decision 8: Foreign Key Cascade Strategy
- **Status:** LOCKED
- **Decision:** Blanket `ON DELETE CASCADE` is strictly prohibited. `CASCADE` is permitted only for true child-owned entities (`KnowledgeDocument -> KnowledgeChunk`, `ConversationSession -> ChatMessage/SearchSnapshot`, `Booking -> BookingItem/HomeVisit`, `Package -> PackageTest`). All historical business references (`LabTest -> Category`, `Booking -> Customer/Branch/Slot`, etc.) enforce `ON DELETE RESTRICT` or `ON DELETE SET NULL`.

---

## Decision 9: Circular Foreign Key Resolution
- **Status:** LOCKED
- **Decision:** The circular reference between `SearchSnapshot.session_id` and `ConversationSession.active_snapshot_id` is resolved using `use_alter=True` on `active_snapshot_id` with `post_update=True` in the SQLAlchemy relationship.
