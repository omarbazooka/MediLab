# 16. Decisions and Open Questions — Phase 4

## Locked Decisions for Phase 4

### Decision 10: Deterministic 30-Minute Slot Scheduling & Concurrency Locking
- **Status:** LOCKED
- **Operating Hours:** Standardized to 09:00 - 19:00 for MVP physical branches.
- **Slot Duration:** 30 minutes (`09:00, 09:30, ..., 18:30`).
- **Closing Time Policy:** 19:00 is closing time, NOT an appointment start.
- **Off-Grid Policy:** Never silently round off-grid times (e.g., 16:05, 16:45). Return an invalid slot error and suggest actual available slots from DB.
- **Default Capacity:** 1 booking per slot for MVP.
- **Row Locking:** `SELECT ... FOR UPDATE` on `AvailabilitySlot` ensures double-booking is impossible under concurrent load.

### Decision 11: Pending Action Protocol and Explicit Confirmation
- **Status:** LOCKED
- **Principle:** "LLM understands. Python verifies. LLM explains."
- **Multi-Turn State:** Persisted in `ConversationSession.pending_action`.
- **Targeted Collection:** Ask only for missing required fields (one question at a time).
- **Confirmation Gate:** Always present an explicit summary (service, branch/address, date, exact time, price, customer name/phone) and require explicit user confirmation before executing any DB mutation.
- **Idempotency:** Unique `idempotency_key` guarantees accidental double-confirmations return the same booking reference without duplicate database rows.
- **Cancellation Scope:** Bookings can only be cancelled by the originating customer/session.

## Open Questions & Future Phase Considerations
- **Resource/Staff Modeling:** (Phase 5+) Currently capacity=1 per slot. Multi-phlebotomist and home visit vehicle routing are deferred to post-MVP.
- **Payment Processing:** Currently appointments snapshot prices for cash/on-arrival payment. Online payment gateways will be integrated in a later phase.
