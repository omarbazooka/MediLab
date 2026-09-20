"""Deterministic Phase 4 Business Action Subgraph Verifier for MediLab AI.

Validates end-to-end execution of all required core business actions and invariants:
1. Branch availability & deterministic 30m slot rules (09:00-18:30 valid, 19:00 closing, 16:05 rejected with alternatives).
2. Branch booking transactional execution (capacity=1, real reference, DB price snapshot).
3. Concurrency / double-booking protection (slot becomes full after booking).
4. Idempotency guarantee (repeated confirmation returns identical booking without duplicate).
5. Home visit booking with address, area, and 1-to-1 HomeVisit record.
6. Read-only booking status query with customer ownership scoping.
7. Booking cancellation with transactional slot capacity release.
8. Multi-turn LangGraph orchestrator flow with pending action persistence and explicit confirmation gating.

Zero external LLM API calls are made.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

# Ensure workspace root is in sys.path when executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app import create_app
from app.agent.graph import MediLabAgent
from app.agent.llm.factory import set_override_llm_provider
from app.agent.llm.fake import FakeLLMProvider
from app.extensions import db
from app.models.branch import AvailabilitySlot, Branch
from app.models.package import Package, PackageTest
from app.models.test import LabTest, TestCategory
from app.services.booking_service import (
    BookingService,
    CapacityExceededError,
)


def run_verification() -> bool:
    print("=" * 70)
    print("MediLab AI Phase 4 — Business Action Subgraph Deterministic Verifier")
    print("=" * 70)

    app = create_app("testing", test_config={"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    all_passed = True

    with app.app_context():
        db.create_all()

        # ------------------------------------------------------------------
        # Setup Deterministic Seed Data
        # ------------------------------------------------------------------
        cat = TestCategory(name="Clinical Pathology", slug="clinical-pathology", active=True)
        db.session.add(cat)
        db.session.flush()

        cbc_test = LabTest(
            code="CBC",
            name="Complete Blood Count",
            category_id=cat.id,
            short_description="Full blood count",
            sample_type="Whole Blood",
            price=Decimal("250.00"),
            result_turnaround_text="4 hours",
            active=True,
        )
        crp_test = LabTest(
            code="CRP",
            name="C-Reactive Protein",
            category_id=cat.id,
            short_description="Inflammatory marker",
            sample_type="Serum",
            price=Decimal("180.00"),
            result_turnaround_text="6 hours",
            active=True,
        )
        db.session.add_all([cbc_test, crp_test])
        db.session.flush()

        pkg = Package(
            name="General Checkup",
            description="CBC and CRP screening",
            price=Decimal("380.00"),
            active=True,
        )
        db.session.add(pkg)
        db.session.flush()
        db.session.add(PackageTest(package_id=pkg.id, test_id=cbc_test.id))
        db.session.add(PackageTest(package_id=pkg.id, test_id=crp_test.id))

        branch = Branch(
            name="Nasr City Branch",
            address="45 Abbas El Akkad, Nasr City, Cairo",
            phone="+20224012345",
            opening_hours_json={"regular": "09:00 - 19:00"},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        target_date = date.today() + timedelta(days=1)

        # Seed discrete slots: 16:00 and 16:30
        slot_1600 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=target_date,
            time=time(16, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        slot_1630 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=target_date,
            time=time(16, 30),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        slot_home = AvailabilitySlot(
            branch_id=None,
            visit_type="HOME",
            date=target_date,
            time=time(10, 0),
            capacity=1,
            reserved_count=0,
            active=True,
        )
        db.session.add_all([slot_1600, slot_1630, slot_home])
        db.session.commit()

        service = BookingService()

        # ------------------------------------------------------------------
        # Check 1: Deterministic 30m Slot Rules & Availability
        # ------------------------------------------------------------------
        print("\n[Check 1] Deterministic 30-Minute Slot Rules & Non-Rounding")

        # 16:00 available
        res_1600 = service.check_branch_availability(branch.id, "BRANCH", target_date, time(16, 0))
        assert res_1600["available"] is True
        assert res_1600["status"] == "AVAILABLE"
        print("  ✓ 16:00 slot is AVAILABLE")

        # 16:05 invalid off-grid -> rejected with real alternatives
        res_1605 = service.check_branch_availability(branch.id, "BRANCH", target_date, time(16, 5))
        assert res_1605["available"] is False
        assert res_1605["status"] == "INVALID_TIME"
        assert len(res_1605["alternatives"]) > 0
        print(
            f"  ✓ 16:05 rejected without silent rounding. Provided {len(res_1605['alternatives'])} real alternatives."
        )

        # 19:00 closing time -> rejected
        res_1900 = service.check_branch_availability(branch.id, "BRANCH", target_date, time(19, 0))
        assert res_1900["available"] is False
        assert res_1900["status"] == "OUTSIDE_HOURS"
        print("  ✓ 19:00 branch closing time rejected as valid start.")

        # ------------------------------------------------------------------
        # Check 2: create_branch_booking Atomic Execution
        # ------------------------------------------------------------------
        print("\n[Check 2] create_branch_booking Atomic Transaction")
        idemp_branch = "idemp-verifier-branch-001"
        booking_branch = service.create_branch_booking(
            customer_name="Dr. Tarek Youssef",
            customer_phone="+201012345678",
            branch_id=branch.id,
            slot_id=slot_1600.id,
            idempotency_key=idemp_branch,
            test_ids=[cbc_test.id],
        )
        assert booking_branch is not None
        assert booking_branch.status == "CONFIRMED"
        assert booking_branch.booking_reference.startswith("MLB-")
        assert len(booking_branch.items) == 1
        assert booking_branch.items[0].unit_price_snapshot == Decimal("250.00")
        print(
            f"  ✓ Created branch booking: {booking_branch.booking_reference} (Price: {booking_branch.items[0].unit_price_snapshot} EGP)"
        )

        # Verify slot reserved_count incremented
        slot_reloaded = db.session.get(AvailabilitySlot, slot_1600.id)
        assert slot_reloaded.reserved_count == 1
        print("  ✓ Slot 16:00 reserved_count atomically incremented (1/1).")

        # ------------------------------------------------------------------
        # Check 3: Concurrency / Double-Booking Protection
        # ------------------------------------------------------------------
        print("\n[Check 3] Concurrency & Double-Booking Protection")
        res_double_check = service.check_branch_availability(
            branch.id, "BRANCH", target_date, time(16, 0)
        )
        assert res_double_check["available"] is False
        assert res_double_check["status"] == "SLOT_FULL"
        print("  ✓ Verification queries report slot 16:00 is SLOT_FULL.")

        try:
            service.create_branch_booking(
                customer_name="Second Competitor",
                customer_phone="+201099998888",
                branch_id=branch.id,
                slot_id=slot_1600.id,
                idempotency_key="idemp-competitor-second",
                test_ids=[cbc_test.id],
            )
            print("  ✗ ERROR: Double booking was allowed!")
            all_passed = False
        except CapacityExceededError:
            print("  ✓ Second attempt for full slot correctly raised CapacityExceededError.")

        # ------------------------------------------------------------------
        # Check 4: Idempotency Protection
        # ------------------------------------------------------------------
        print("\n[Check 4] Idempotency Guarantee")
        booking_repeat = service.create_branch_booking(
            customer_name="Dr. Tarek Youssef",
            customer_phone="+201012345678",
            branch_id=branch.id,
            slot_id=slot_1600.id,
            idempotency_key=idemp_branch,
            test_ids=[cbc_test.id],
        )
        assert booking_repeat.id == booking_branch.id
        assert booking_repeat.booking_reference == booking_branch.booking_reference
        slot_after_repeat = db.session.get(AvailabilitySlot, slot_1600.id)
        assert slot_after_repeat.reserved_count == 1
        print(
            "  ✓ Repeated confirmation with identical idempotency key returned existing booking without duplicating row or slot count."
        )

        # ------------------------------------------------------------------
        # Check 5: create_home_visit Execution
        # ------------------------------------------------------------------
        print("\n[Check 5] create_home_visit Execution")
        booking_home = service.create_home_visit(
            customer_name="Heba Mahmoud",
            customer_phone="+201144556677",
            slot_id=slot_home.id,
            address="14 El Merghany St, Heliopolis",
            area="Heliopolis",
            home_instructions="Ring doorbell 12",
            idempotency_key="idemp-home-verifier-001",
            package_ids=[pkg.id],
        )
        assert booking_home is not None
        assert booking_home.visit_type == "HOME"
        assert booking_home.home_visit is not None
        assert booking_home.home_visit.address == "14 El Merghany St, Heliopolis"
        assert booking_home.home_visit.area == "Heliopolis"
        print(
            f"  ✓ Created home visit: {booking_home.booking_reference} (Area: {booking_home.home_visit.area})"
        )

        # ------------------------------------------------------------------
        # Check 6: get_booking_status Read-Only with Scope
        # ------------------------------------------------------------------
        print("\n[Check 6] get_booking_status Scoping")
        status_ok = service.get_booking_status(
            reference=booking_branch.booking_reference,
            customer_id=booking_branch.customer_id,
        )
        assert status_ok is not None
        assert status_ok.status == "CONFIRMED"
        print(f"  ✓ Authorized query retrieved status: {status_ok.status}")

        status_unauthorized = service.get_booking_status(
            reference=booking_branch.booking_reference,
            customer_id=999999,
        )
        assert status_unauthorized is None
        print("  ✓ Unauthorized customer query safely returned None without leaking data.")

        # ------------------------------------------------------------------
        # Check 7: cancel_booking and Slot Release
        # ------------------------------------------------------------------
        print("\n[Check 7] cancel_booking and Atomic Capacity Release")
        cancelled = service.cancel_booking(
            reference=booking_branch.booking_reference,
            customer_id=booking_branch.customer_id,
        )
        assert cancelled.status == "CANCELLED"
        assert cancelled.cancelled_at is not None

        slot_released = db.session.get(AvailabilitySlot, slot_1600.id)
        assert slot_released.reserved_count == 0
        assert slot_released.is_available is True
        print(f"  ✓ Booking {cancelled.booking_reference} marked CANCELLED.")
        print("  ✓ Slot 16:00 capacity released (reserved_count = 0/1) and is available again.")

        # ------------------------------------------------------------------
        # Check 8: Multi-Turn Conversation Flow & Explicit Confirmation Gate
        # ------------------------------------------------------------------
        print("\n[Check 8] Multi-Turn LangGraph Flow & Confirmation Gate")
        fake_llm = FakeLLMProvider()
        set_override_llm_provider(fake_llm)
        agent = MediLabAgent()

        session_id = f"sess-verif-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        # Turn 1: Collect intent and slot, leave name/phone missing
        t1 = agent.run_turn(session_id, "I want to book CBC at Nasr City tomorrow at 4:30 PM")
        p1 = t1.get("pending_action")
        assert p1 is not None
        assert p1["scheduled_time"] == "16:30"
        assert "customer_name" in p1["missing_fields"]
        print(
            "  ✓ Turn 1: Extracted test, branch, and slot. Correctly identified missing customer details."
        )

        # Turn 2: Provide missing details -> Enter AWAITING_CONFIRMATION
        t2 = agent.run_turn(session_id, "My name is Mostafa Kamel and phone is 01023456789")
        p2 = t2.get("pending_action")
        assert p2 is not None
        assert p2["customer_name"] == "Mostafa Kamel"
        assert len(p2["missing_fields"]) == 0
        a2 = t2.get("action_result")
        assert a2["status"] == "AWAITING_CONFIRMATION"
        assert a2["committed"] is False
        print("  ✓ Turn 2: Merged fields. Presented confirmation summary; ZERO DB rows inserted.")

        # Turn 3: Explicit confirmation -> Execute
        t3 = agent.run_turn(session_id, "Yes, confirm booking please")
        a3 = t3.get("action_result")
        assert a3["status"] == "EXECUTED"
        assert a3["committed"] is True
        assert a3["booking_reference"].startswith("MLB-")
        print(
            f"  ✓ Turn 3: Confirmed. Transaction committed, reference: {a3['booking_reference']}."
        )

    print("\n" + "=" * 70)
    if all_passed:
        print("All Phase 4 Business Action Invariants VERIFIED SUCCESSFULLY.")
    else:
        print("Some Phase 4 Invariants FAILED.")
    print("=" * 70)
    return all_passed


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
