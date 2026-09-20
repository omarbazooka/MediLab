# 05. Database and ORM Design — Phase 4 Availability & Business Actions

## Overview
This document records the data model invariants, slot generation architecture, and transactional locking mechanics for MediLab AI Phase 4 (Business Action Subgraph).

## Core Entities & Invariants

### 1. Branches (`branches`)
- `opening_hours_json`: Standardized to `09:00 - 19:00` for all physical branches.
- `active`: Boolean flag indicating whether the branch is operational.
- Inactive branches cannot accept new slot bookings.

### 2. Availability Slots (`availability_slots`)
- `visit_type`: `'BRANCH'` or `'HOME'`.
- `branch_id`: Foreign key to `branches.id` for `'BRANCH'`, `NULL` for `'HOME'`.
- `date`: Appointment date (`DATE`).
- `time`: Appointment start time (`TIME`).
  - Strict 30-minute interval grid: `09:00, 09:30, 10:00, 10:30, ..., 18:30`.
  - Closing time `19:00` is NOT a valid start time.
  - Off-grid times (e.g., `16:05`, `16:15`, `16:45`) are invalid; silent rounding is strictly prohibited.
- `capacity`: Default `1` per 30-minute slot for MVP.
- `reserved_count`: Incremented on confirmed booking, decremented on cancellation.
- Invariants:
  - `ck_slots_capacity_non_negative`: `capacity >= 0`
  - `ck_slots_reserved_non_negative`: `reserved_count >= 0`
  - `ck_slots_reserved_le_capacity`: `reserved_count <= capacity`
  - `ck_slots_visit_type`: `visit_type IN ('BRANCH', 'HOME')`
  - `ck_slots_branch_for_branch_visit`: `(visit_type = 'BRANCH' AND branch_id IS NOT NULL) OR (visit_type = 'HOME' AND branch_id IS NULL)`
- Partial Uniqueness:
  - `uq_slots_branch_date_time`: `(branch_id, date, time)` unique where `visit_type = 'BRANCH'`.
  - `uq_slots_home_date_time`: `(date, time)` unique where `visit_type = 'HOME' AND branch_id IS NULL`.

### 3. Bookings (`bookings`)
- `booking_reference`: Collision-safe alphanumeric code: `MLB-YYYYMMDD-XXXXXXXX` (unique, indexed).
- `customer_id`: Foreign key to `customers.id` (`ON DELETE RESTRICT`).
- `availability_slot_id`: Authoritative link to `availability_slots.id` (`ON DELETE RESTRICT`).
- `visit_type`: `'BRANCH'` or `'HOME'`.
- `branch_id`: Snapshot of physical branch (`NULL` for `'HOME'`).
- `scheduled_date` & `scheduled_time`: Snapshot of appointment date and time.
- `status`: `'CONFIRMED'`, `'COMPLETED'`, or `'CANCELLED'`.
- `idempotency_key`: Unique string identifier provided by client/session to guarantee zero duplicate bookings.
- `cancelled_at`: Timestamp recorded upon cancellation.

### 4. Booking Items (`booking_items`)
- `booking_id`: Foreign key to `bookings.id` (`ON DELETE CASCADE`).
- `test_id`: Foreign key to `lab_tests.id` (`NULL` if package).
- `package_id`: Foreign key to `packages.id` (`NULL` if test).
- `unit_price_snapshot`: Exact `NUMERIC(10, 2)` price snapshot at the moment of booking from active catalog row.
- Constraint: Exactly one of `test_id` or `package_id` must be non-null.

### 5. Home Visits (`home_visits`)
- Associated 1-to-1 with `bookings.id` (`ON DELETE CASCADE`).
- Fields: `address`, `area`, `instructions`, `status` (`'SCHEDULED'`, `'CANCELLED'`, etc.).

---

## Concurrency & Transactional Locking

### Double-Booking Protection
When executing a booking transaction:
1. `SELECT ... FOR UPDATE` acquires an exclusive row-level lock on the target `AvailabilitySlot`.
2. Verified preconditions:
   - Slot exists and is `active == True`.
   - `reserved_count < capacity`.
3. If capacity is already exhausted (`reserved_count >= capacity`), the transaction raises `CapacityExceededError` and aborts before creating any booking records.
4. If two concurrent workers target the same slot, the first to acquire the lock completes and commits; the second immediately observes `reserved_count == capacity` and is rejected cleanly.

### Idempotency Enforcement
1. Before taking locks, query `bookings` by `idempotency_key`. If an existing booking exists, return it immediately without taking locks or incrementing slot capacity.
2. In the rare event of a concurrent race on the same `idempotency_key`, the unique DB constraint triggers an `IntegrityError`, prompting a rollback and re-query to return the winning booking row.

### Safe Slot Release upon Cancellation
1. `SELECT ... FOR UPDATE` acquires an exclusive lock on the `Booking` row.
2. If already `CANCELLED`, return idempotently.
3. Acquire `SELECT ... FOR UPDATE` lock on the linked `AvailabilitySlot`.
4. Decrement slot `reserved_count = max(reserved_count - 1, 0)`.
5. Update `booking.status = 'CANCELLED'` and `booking.cancelled_at = now()`.
6. Update `home_visit.status = 'CANCELLED'` if applicable.
7. Commit transaction.
