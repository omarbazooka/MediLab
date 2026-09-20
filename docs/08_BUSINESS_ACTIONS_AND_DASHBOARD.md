# 08. Business Actions and Subgraph — Phase 4

## Overview
Phase 4 integrates four core deterministic business actions into the MediLab AI LangGraph orchestrator:
1. `create_branch_booking`: Books an in-branch lab test or package appointment.
2. `create_home_visit`: Schedules a home sample collection visit.
3. `get_booking_status`: Read-only inquiry for an existing booking reference within session ownership scope.
4. `cancel_booking`: Cancels an active booking, decrements the slot reserved count, and releases capacity.

---

## The Principle: "LLM Understands. Python Verifies. LLM Explains."

1. **LLM Responsibilities:**
   - Intent recognition (`BOOK_BRANCH_VISIT`, `BOOK_HOME_VISIT`, `CHECK_BOOKING`, `CANCEL_BOOKING`).
   - Slot and customer entity extraction (date, time, service name, branch name, customer name, phone, address).
   - Natural language dialogue phrasing for missing field questions, confirmation summaries, and outcomes.

2. **Deterministic Service Responsibilities:**
   - Catalog entity resolution (test ID, package ID, price snapshot).
   - Branch ID and operational status verification.
   - Operating hours and 30-minute interval validation (rejecting non-30m off-grid times without silent rounding).
   - Capacity verification and row-level locking (`SELECT ... FOR UPDATE`).
   - Ownership verification for read/cancellation operations.
   - Idempotency key generation and validation.
   - Transactional commit and rollback safety.

---

## Multi-Turn Pending Action Lifecycle

Mutating operations (`create_branch_booking`, `create_home_visit`, `cancel_booking`) persist their state in `ConversationSession.pending_action`:

```json
{
  "action_id": "uuid-string",
  "action_type": "CREATE_BRANCH_BOOKING",
  "test_id": 1,
  "test_name": "Complete Blood Count (CBC)",
  "package_id": null,
  "package_name": null,
  "visit_type": "BRANCH",
  "branch_id": 1,
  "branch_name": "Nasr City Branch",
  "customer_name": "Ahmed Ali",
  "customer_phone": "01012345678",
  "customer_email": null,
  "scheduled_date": "2026-09-21",
  "scheduled_time": "16:00:00",
  "slot_id": 42,
  "address": null,
  "area": null,
  "notes": null,
  "booking_reference": null,
  "missing_fields": [],
  "confirmation_state": "AWAITING_CONFIRMATION",
  "idempotency_key": "deterministic-hash",
  "summary": { ... },
  "completed_reference": null
}
```

### Flow Steps
1. **Extraction & Merge:** User provides partial details. LLM extracts entities; service merges them into existing or new `pending_action`.
2. **Deterministic Validation:**
   - Slot exists, branch open (09:00 - 19:00), time is valid 30-minute slot, capacity remaining.
   - If slot is invalid/full, service recomputes alternatives and prompts user with real nearby slots.
3. **Missing Fields Check:**
   - If required fields are missing (e.g. phone or name), set `confirmation_state = 'COLLECTING'`.
   - Ask **one targeted question** for the missing fields. Do not attempt database mutation.
4. **Explicit Confirmation Summary:**
   - Once all required fields are valid, present a full appointment summary (service, branch/address, date, exact time, price, customer).
   - Set `confirmation_state = 'AWAITING_CONFIRMATION'`.
   - Require explicit customer affirmation ("Confirm", "Yes", "أكد").
5. **Atomic Execution:**
   - Only upon explicit confirmation: begin transaction, acquire row lock on `AvailabilitySlot`, re-verify capacity, insert customer, insert booking, insert booking item(s), increment slot `reserved_count`, commit.
   - Return real booking reference `MLB-YYYYMMDD-XXXXXXXX`.
   - Clear/complete `pending_action`.
   - Repeated confirmations return the existing booking idempotently without double-booking.
