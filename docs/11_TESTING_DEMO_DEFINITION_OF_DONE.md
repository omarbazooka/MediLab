# 11. Testing, Demo, and Definition of Done — Phase 4

## Phase 4 Definition of Done (DoD)

Phase 4 is TESTED and ready for code review when:
1. **Branch Booking:** Confirmed booking writes a real `bookings` row, creates `booking_items` with catalog price snapshot, increments `reserved_count` on `availability_slots`.
2. **Home Visit:** Confirmed home visit writes a `bookings` row with linked `home_visits` record.
3. **Status Check:** Reads real DB status without hallucinating or leaking across session scopes.
4. **Cancellation:** Changes booking to `CANCELLED`, sets `cancelled_at`, decrements `reserved_count` on linked slot, releases slot for re-booking.
5. **Exact 30-Minute Rules:** Only 30-minute intervals between 09:00 and 18:30 are valid. Times like 16:05 or 19:00 are rejected without silent rounding.
6. **Double-Booking Protection:** Concurrent attempts on a slot with capacity 1 result in exactly one successful booking and one controlled rejection.
7. **Idempotency:** Repeated confirmations yield the same booking reference with zero duplicate rows.
8. **Rollback Safety:** Any failure in the booking transaction rolls back cleanly with zero partial state.
9. **Multi-Turn State:** `pending_action` persists across conversational turns and asks only for missing fields.
10. **Zero Real Gemini Calls:** During quota cooldown, all tests and verifications execute using deterministic test doubles.

## Test Verification Matrix (35 Minimum Requirements)
- **Availability (1–8):** Free slot, full slot, independent slot, off-grid invalid time, pre-opening, closing time, inactive slot, inactive branch.
- **Booking (9–17):** Missing fields rejection, valid confirmed single row, home visit row, unconfirmed no-op, idempotent duplicate confirmation, reference formatting, price snapshotting, capacity increment.
- **Concurrency & Reliability (18–21):** Transaction failure rollback, no success claim on rollback, concurrent capacity race locking, idempotency survival.
- **Cancellation (22–26):** CANCELLED status update, slot capacity release, re-booking released slot, idempotent repeated cancellation, cross-session isolation.
- **Status (27–29):** Known reference truthful status, unknown reference handling, cross-session scope protection.
- **Conversation (30–35):** `pending_action` persistence, multi-turn field merging, targeted missing field question, explicit confirmation requirement, pending action cleanup on success, session isolation.
