"""Comprehensive PostgreSQL integration tests for MediLab AI Phase 1.

Tests real PostgreSQL behaviors:
- VECTOR(384) column operations
- Automatic FTS search_vector trigger maintenance
- Partial unique index enforcement on AvailabilitySlot
- Child-owned cascade vs historical reference RESTRICT
- Circular FK resolution between ConversationSession and SearchSnapshot
- BookingService concurrency, atomic slot locking, idempotency, and rollback
- Seed script idempotency
"""

from __future__ import annotations

import concurrent.futures
import secrets
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.extensions import db
from app.models.booking import Booking
from app.models.branch import AvailabilitySlot, Branch
from app.models.conversation import ConversationSession
from app.models.customer import Customer
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.package import Package, PackageTest
from app.models.snapshot import SearchSnapshot
from app.models.test import LabTest, TestCategory
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.customer_repository import CustomerRepository
from app.services.booking_service import (
    BookingService,
    BookingValidationError,
    CapacityExceededError,
)
from app.services.branch_service import BranchService
from scripts.seed_db import run_seed

pytestmark = pytest.mark.postgres


def test_vector_column_storage_and_similarity(postgres_app) -> None:
    """Verify pgvector VECTOR(384) storage and cosine distance operator."""
    with postgres_app.app_context():
        doc = KnowledgeDocument(
            title="Vector Test Doc",
            category="Testing",
            content="Document for vector indexing test.",
            index_status="PENDING",
        )
        db.session.add(doc)
        db.session.flush()

        vec1 = [0.1] * 384
        vec2 = [0.1] * 384
        vec2[0] = 0.9

        chunk = KnowledgeChunk(
            document_id=doc.id,
            chunk_index=0,
            content="First chunk for vector verification.",
            embedding=vec1,
            metadata_={"test": True},
        )
        db.session.add(chunk)
        db.session.commit()

        # Query using vector cosine distance operator (<=>)
        result = (
            db.session.execute(
                text(
                    "SELECT id, embedding <=> :query_vec AS distance "
                    "FROM knowledge_chunks WHERE id = :chunk_id"
                ),
                {"query_vec": str(vec2), "chunk_id": chunk.id},
            )
            .mappings()
            .one()
        )

        assert result["id"] == chunk.id
        assert float(result["distance"]) > 0.0

        # Clean up
        db.session.delete(doc)
        db.session.commit()


def test_fts_trigger_automatic_update(postgres_app) -> None:
    """Verify PostgreSQL trigger automatically maintains search_vector on INSERT and UPDATE."""
    with postgres_app.app_context():
        doc = KnowledgeDocument(
            title="FTS Trigger Doc",
            category="Preparation",
            content="Instructions container",
            index_status="PENDING",
        )
        db.session.add(doc)
        db.session.flush()

        # 1. INSERT chunk
        chunk = KnowledgeChunk(
            document_id=doc.id,
            chunk_index=0,
            content="Patient must be fasting for 12 hours before lipid profile test.",
            metadata_={"source": "prep_guide"},
        )
        db.session.add(chunk)
        db.session.commit()

        # Verify search_vector was populated by trigger with 'simple' configuration
        match_insert = db.session.execute(
            text(
                "SELECT count(*) FROM knowledge_chunks "
                "WHERE id = :id AND search_vector @@ to_tsquery('simple', 'fasting & lipid')"
            ),
            {"id": chunk.id},
        ).scalar()
        assert match_insert == 1

        # 2. UPDATE content
        chunk.content = "Special clean catch urine collection instructions for culture."
        db.session.commit()

        # Verify search_vector updated and matches new content
        match_update = db.session.execute(
            text(
                "SELECT count(*) FROM knowledge_chunks "
                "WHERE id = :id AND search_vector @@ to_tsquery('simple', 'urine & culture')"
            ),
            {"id": chunk.id},
        ).scalar()
        assert match_update == 1

        # Old tokens should no longer match
        match_old = db.session.execute(
            text(
                "SELECT count(*) FROM knowledge_chunks "
                "WHERE id = :id AND search_vector @@ to_tsquery('simple', 'lipid')"
            ),
            {"id": chunk.id},
        ).scalar()
        assert match_old == 0

        # Clean up
        db.session.delete(doc)
        db.session.commit()


def test_availability_slot_partial_uniqueness(postgres_app) -> None:
    """Verify distinct partial uniqueness for BRANCH and HOME slots."""
    with postgres_app.app_context():
        branch = Branch(
            name="Uniqueness Branch",
            address="10 Road",
            phone="+2020000000",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        test_date = date(2026, 10, 1)
        test_time = time(10, 0)

        # 1. Branch slot uniqueness: same branch, date, time must fail
        slot_b1 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=test_date,
            time=test_time,
            capacity=3,
        )
        db.session.add(slot_b1)
        db.session.commit()

        slot_b2 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=test_date,
            time=test_time,
            capacity=3,
        )
        db.session.add(slot_b2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # 2. Home slot uniqueness: date, time with branch_id=NULL must fail on duplicate
        slot_h1 = AvailabilitySlot(
            branch_id=None,
            visit_type="HOME",
            date=test_date,
            time=test_time,
            capacity=2,
        )
        db.session.add(slot_h1)
        db.session.commit()

        slot_h2 = AvailabilitySlot(
            branch_id=None,
            visit_type="HOME",
            date=test_date,
            time=test_time,
            capacity=2,
        )
        db.session.add(slot_h2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # 3. Clean up
        db.session.delete(slot_h1)
        db.session.delete(slot_b1)
        db.session.delete(branch)
        db.session.commit()


def test_cascade_and_restrict_rules(postgres_app) -> None:
    """Verify child-owned entities cascade delete while business references are restricted."""
    with postgres_app.app_context():
        # Setup category and test
        cat = TestCategory(name="Cascade Cat", slug="cascade-cat")
        db.session.add(cat)
        db.session.flush()

        lab_test = LabTest(
            category_id=cat.id,
            code="CASC_TEST",
            name="Cascade Test",
            short_description="Desc",
            sample_type="Blood",
            price=Decimal("100.00"),
            result_turnaround_text="2h",
        )
        db.session.add(lab_test)
        db.session.commit()

        # RESTRICT check: Deleting category with active lab_test must fail
        db.session.delete(cat)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Package -> PackageTest CASCADE check
        pkg = Package(name="Cascade Package", description="Desc", price=Decimal("200.00"))
        db.session.add(pkg)
        db.session.flush()

        # Re-fetch test after rollback
        lab_test = db.session.execute(
            select(LabTest).where(LabTest.code == "CASC_TEST")
        ).scalar_one()
        pkg_test = PackageTest(package_id=pkg.id, test_id=lab_test.id)
        db.session.add(pkg_test)
        db.session.commit()

        # Deleting Package should cascade delete PackageTest
        pkg_id = pkg.id
        db.session.delete(pkg)
        db.session.commit()

        remaining_pt = db.session.execute(
            select(PackageTest).where(PackageTest.package_id == pkg_id)
        ).scalar_one_or_none()
        assert remaining_pt is None

        # Clean up
        cat = db.session.execute(
            select(TestCategory).where(TestCategory.slug == "cascade-cat")
        ).scalar_one()
        db.session.delete(lab_test)
        db.session.delete(cat)
        db.session.commit()


def test_circular_fk_conversation_and_snapshot(postgres_app) -> None:
    """Verify resolution of circular FK between ConversationSession and SearchSnapshot."""
    with postgres_app.app_context():
        session = ConversationSession(
            session_id="cycle-session-1",
            current_state={"step": "searching"},
        )
        db.session.add(session)
        db.session.flush()

        snapshot = SearchSnapshot(
            session_id=session.session_id,
            sequence_no=1,
            query="Complete Blood Count",
            criteria={"category": "hematology"},
            items=[{"index": 1, "code": "CBC", "name": "Complete Blood Count"}],
            status="ACTIVE",
        )
        db.session.add(snapshot)
        db.session.flush()

        session.active_snapshot_id = snapshot.id
        db.session.commit()

        # Verify relationship loads bidirectionally
        reloaded_session = db.session.execute(
            select(ConversationSession).where(ConversationSession.session_id == "cycle-session-1")
        ).scalar_one()
        assert reloaded_session.active_snapshot is not None
        assert reloaded_session.active_snapshot.id == snapshot.id
        assert len(reloaded_session.snapshots) == 1

        # Delete session: should cascade delete snapshot and clear active_snapshot_id cleanly
        db.session.delete(reloaded_session)
        db.session.commit()

        remaining_snap = db.session.execute(
            select(SearchSnapshot).where(SearchSnapshot.id == snapshot.id)
        ).scalar_one_or_none()
        assert remaining_snap is None


def test_booking_service_transactional_workflow(postgres_app) -> None:
    """Verify BookingService atomic slot locking, overbooking prevention, and idempotency."""
    import secrets

    suffix = secrets.token_hex(3)
    with postgres_app.app_context():
        # Create branch, slot with capacity=1, category, and test
        branch = Branch(
            name=f"Service Branch {suffix}",
            address="1 Test St",
            phone=f"+2011{suffix[:4]}",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        slot = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 11, 1),
            time=time(9, 0),
            capacity=1,  # Single appointment capacity
            reserved_count=0,
            active=True,
        )
        db.session.add(slot)
        db.session.flush()

        cat = TestCategory(name=f"Service Cat {suffix}", slug=f"service-cat-{suffix}")
        db.session.add(cat)
        db.session.flush()

        lab_test = LabTest(
            category_id=cat.id,
            code=f"SRV_{suffix}",
            name=f"Service Test {suffix}",
            short_description="Desc",
            sample_type="Serum",
            price=Decimal("150.00"),
            result_turnaround_text="2h",
            active=True,
        )
        db.session.add(lab_test)
        db.session.commit()

        service = BookingService()

        # 1. First booking succeeds
        booking1 = service.create_booking(
            customer_name="Tariq Ali",
            customer_phone=f"+20101{suffix[:5]}",
            slot_id=slot.id,
            visit_type="BRANCH",
            idempotency_key=f"idemp-{suffix}-001",
            branch_id=branch.id,
            test_ids=[lab_test.id],
        )
        assert booking1.booking_reference.startswith("MLB-")
        assert booking1.status == "CONFIRMED"
        assert booking1.availability_slot_id == slot.id

        # Verify slot reserved_count is incremented to 1
        db.session.refresh(slot)
        assert slot.reserved_count == 1

        # 2. Idempotency test: Re-submitting identical idempotency_key returns existing booking
        booking1_repeat = service.create_booking(
            customer_name="Tariq Ali",
            customer_phone=f"+20101{suffix[:5]}",
            slot_id=slot.id,
            visit_type="BRANCH",
            idempotency_key=f"idemp-{suffix}-001",
            branch_id=branch.id,
            test_ids=[lab_test.id],
        )
        assert booking1_repeat.id == booking1.id
        db.session.refresh(slot)
        assert slot.reserved_count == 1  # Not double incremented

        # 3. Capacity exceeded test: Second distinct customer booking same full slot fails
        with pytest.raises(CapacityExceededError):
            service.create_booking(
                customer_name="Sara Nour",
                customer_phone=f"+20109{suffix[:5]}",
                slot_id=slot.id,
                visit_type="BRANCH",
                idempotency_key=f"idemp-{suffix}-002",
                branch_id=branch.id,
                test_ids=[lab_test.id],
            )

        # 4. Rollback test: Invalid test ID raises error and rolls back slot reserved_count
        slot2 = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 11, 2),
            time=time(10, 0),
            capacity=2,
            reserved_count=0,
            active=True,
        )
        db.session.add(slot2)
        db.session.commit()

        with pytest.raises(BookingValidationError):
            service.create_booking(
                customer_name="Sara Nour",
                customer_phone=f"+20109{suffix[:5]}",
                slot_id=slot2.id,
                visit_type="BRANCH",
                idempotency_key=f"idemp-{suffix}-003",
                branch_id=branch.id,
                test_ids=[999999],  # Non-existent test
            )
        db.session.refresh(slot2)
        assert slot2.reserved_count == 0  # Rolled back, zero change

        # 5. Cancellation test: releases slot capacity
        cancelled_booking = service.cancel_booking(booking1.booking_reference)
        assert cancelled_booking.status == "CANCELLED"
        db.session.refresh(slot)
        assert slot.reserved_count == 0  # Capacity freed

        # Clean up
        db.session.delete(cancelled_booking)
        db.session.delete(slot)
        db.session.delete(slot2)
        db.session.delete(lab_test)
        db.session.delete(cat)
        db.session.delete(branch)


def test_home_booking_integration_and_constraint(postgres_app) -> None:
    """Verify HOME booking integration: slot, home_visit 1:1, branch_id IS NULL, and DB constraint."""
    suffix = secrets.token_hex(4)
    with postgres_app.app_context():
        # 1. Setup category, test, and HOME slot
        cat = TestCategory(name=f"Home Cat {suffix}", slug=f"home-cat-{suffix}")
        db.session.add(cat)
        db.session.flush()

        lab_test = LabTest(
            category_id=cat.id,
            code=f"HT_{suffix}",
            name=f"Home Test {suffix}",
            short_description="Desc",
            sample_type="Blood",
            price=Decimal("250.00"),
            result_turnaround_text="24h",
            active=True,
        )
        db.session.add(lab_test)
        db.session.flush()

        day = (int(suffix, 16) % 25) + 1
        hour = (int(suffix, 16) % 12) + 8
        minute = (int(suffix, 16) % 4) * 15
        slot = AvailabilitySlot(
            branch_id=None,
            visit_type="HOME",
            date=date(2026, 12, day),
            time=time(hour, minute),
            capacity=3,
            reserved_count=0,
            active=True,
        )
        db.session.add(slot)
        db.session.commit()

        service = BookingService()

        # 2. Successfully create HOME booking
        booking = service.create_booking(
            customer_name="Mona Zaki",
            customer_phone=f"+20102{suffix[:6]}",
            slot_id=slot.id,
            visit_type="HOME",
            address="123 Nile Corniche, 4th Floor, Apt 8",
            area="Maadi",
            home_instructions="Ring bell twice",
            idempotency_key=f"home-{suffix}",
            test_ids=[lab_test.id],
        )

        assert booking.visit_type == "HOME"
        assert booking.branch_id is None
        assert booking.home_visit is not None
        assert booking.home_visit.booking_id == booking.id
        assert booking.home_visit.address == "123 Nile Corniche, 4th Floor, Apt 8"
        assert booking.home_visit.area == "Maadi"
        assert booking.home_visit.instructions == "Ring bell twice"
        assert booking.home_visit.status == "SCHEDULED"

        db.session.refresh(slot)
        assert slot.reserved_count == 1

        # 3. Strengthened check constraint test:
        # A) HOME booking with branch_id NOT NULL must be rejected by PostgreSQL
        branch = Branch(
            name=f"Branch {suffix}",
            address="Test St",
            phone=f"+20103{suffix[:6]}",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.commit()

        invalid_home = Booking(
            customer_id=booking.customer_id,
            availability_slot_id=slot.id,
            visit_type="HOME",
            branch_id=branch.id,  # VIOLATION: HOME must have branch_id IS NULL
            scheduled_date=slot.date,
            scheduled_time=slot.time,
            status="CONFIRMED",
            booking_reference=f"MLB-ERR1-{suffix[:6]}",
            idempotency_key=f"err1-{suffix}",
        )
        db.session.add(invalid_home)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # B) BRANCH booking with branch_id IS NULL must also be rejected
        invalid_branch = Booking(
            customer_id=booking.customer_id,
            availability_slot_id=slot.id,
            visit_type="BRANCH",
            branch_id=None,  # VIOLATION: BRANCH must have branch_id IS NOT NULL
            scheduled_date=slot.date,
            scheduled_time=slot.time,
            status="CONFIRMED",
            booking_reference=f"MLB-ERR2-{suffix[:6]}",
            idempotency_key=f"err2-{suffix}",
        )
        db.session.add(invalid_branch)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Cleanup
        b = db.session.get(Booking, booking.id)
        if b:
            db.session.delete(b)
        s = db.session.get(AvailabilitySlot, slot.id)
        if s:
            db.session.delete(s)
        t = db.session.get(LabTest, lab_test.id)
        if t:
            db.session.delete(t)
        c = db.session.get(TestCategory, cat.id)
        if c:
            db.session.delete(c)
        br = db.session.get(Branch, branch.id)
        if br:
            db.session.delete(br)
        db.session.commit()


def test_concurrent_cancellation_locking(postgres_app) -> None:
    """Verify concurrent cancel_booking calls on the same booking lock row and decrement reserved_count exactly once."""
    suffix = secrets.token_hex(4)
    with postgres_app.app_context():
        branch = Branch(
            name=f"Cancel Branch {suffix}",
            address="Cancel St",
            phone=f"+20104{suffix[:6]}",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        slot = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 11, 15),
            time=time(11, 0),
            capacity=2,
            reserved_count=0,
            active=True,
        )
        db.session.add(slot)
        db.session.flush()

        cat = TestCategory(name=f"Cancel Cat {suffix}", slug=f"cancel-cat-{suffix}")
        db.session.add(cat)
        db.session.flush()

        lab_test = LabTest(
            category_id=cat.id,
            code=f"CT_{suffix}",
            name=f"Cancel Test {suffix}",
            short_description="Desc",
            sample_type="Blood",
            price=Decimal("120.00"),
            result_turnaround_text="1h",
            active=True,
        )
        db.session.add(lab_test)
        db.session.commit()

        service = BookingService()
        booking = service.create_booking(
            customer_name="Sameh Nabil",
            customer_phone=f"+20105{suffix[:6]}",
            slot_id=slot.id,
            visit_type="BRANCH",
            branch_id=branch.id,
            idempotency_key=f"cancel-concur-{suffix}",
            test_ids=[lab_test.id],
        )

        db.session.refresh(slot)
        assert slot.reserved_count == 1
        booking_ref = booking.booking_reference
        booking_id = booking.id
        slot_id = slot.id
        branch_id = branch.id
        lab_test_id = lab_test.id
        cat_id = cat.id

    # Concurrently execute cancel_booking from two independent sessions/threads
    def run_cancellation():
        with postgres_app.app_context():
            srv = BookingService()
            res = srv.cancel_booking(booking_ref)
            return res.status

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_cancellation)
        f2 = executor.submit(run_cancellation)
        status1 = f1.result()
        status2 = f2.result()

    assert status1 == "CANCELLED"
    assert status2 == "CANCELLED"

    with postgres_app.app_context():
        reloaded_slot = db.session.get(AvailabilitySlot, slot_id)
        assert reloaded_slot is not None
        # Capacity MUST be 0, never negative (-1) from double-decrement
        assert reloaded_slot.reserved_count == 0

        # Cleanup
        b = db.session.get(Booking, booking_id)
        if b:
            db.session.delete(b)
        db.session.delete(reloaded_slot)
        db.session.delete(db.session.get(LabTest, lab_test_id))
        db.session.delete(db.session.get(TestCategory, cat_id))
        db.session.delete(db.session.get(Branch, branch_id))
        db.session.commit()


def test_concurrent_idempotency_and_customer_race(postgres_app) -> None:
    """Verify concurrent requests with same idempotency_key or customer phone resolve deterministically."""
    suffix = secrets.token_hex(4)
    with postgres_app.app_context():
        branch = Branch(
            name=f"Idemp Branch {suffix}",
            address="Idemp St",
            phone=f"+20106{suffix[:6]}",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        slot = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 11, 20),
            time=time(14, 0),
            capacity=5,
            reserved_count=0,
            active=True,
        )
        db.session.add(slot)
        db.session.flush()

        cat = TestCategory(name=f"Idemp Cat {suffix}", slug=f"idemp-cat-{suffix}")
        db.session.add(cat)
        db.session.flush()

        lab_test = LabTest(
            category_id=cat.id,
            code=f"IDT_{suffix}",
            name=f"Idemp Test {suffix}",
            short_description="Desc",
            sample_type="Blood",
            price=Decimal("180.00"),
            result_turnaround_text="2h",
            active=True,
        )
        db.session.add(lab_test)
        db.session.commit()

        slot_id = slot.id
        branch_id = branch.id
        lab_test_id = lab_test.id
        cat_id = cat.id

    # 1. Concurrent create_booking with identical idempotency_key
    shared_key = f"concurrent-idemp-{suffix}"
    customer_phone = f"+20107{suffix[:6]}"

    def run_concurrent_booking():
        with postgres_app.app_context():
            srv = BookingService()
            res = srv.create_booking(
                customer_name="Amr Diab",
                customer_phone=customer_phone,
                slot_id=slot_id,
                visit_type="BRANCH",
                branch_id=branch_id,
                idempotency_key=shared_key,
                test_ids=[lab_test_id],
            )
            return res.id, res.booking_reference

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_concurrent_booking)
        f2 = executor.submit(run_concurrent_booking)
        book1_id, book1_ref = f1.result()
        book2_id, book2_ref = f2.result()

    assert book1_id == book2_id
    assert book1_ref == book2_ref

    with postgres_app.app_context():
        reloaded_slot = db.session.get(AvailabilitySlot, slot_id)
        assert (
            reloaded_slot.reserved_count == 1
        )  # Exactly 1 increment despite 2 concurrent requests

    # 2. Concurrent customer phone race condition in CustomerRepository.get_or_create
    shared_phone = f"+20108{suffix[:6]}"

    def run_customer_create():
        with postgres_app.app_context():
            repo = CustomerRepository()
            res = repo.get_or_create(
                name="Concurrent Customer",
                phone=shared_phone,
                email="concur@example.com",
            )
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                res = repo.get_by_phone(shared_phone)
            return res.id, res.phone

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        cf1 = executor.submit(run_customer_create)
        cf2 = executor.submit(run_customer_create)
        c1_id, c1_phone = cf1.result()
        c2_id, c2_phone = cf2.result()

    assert c1_id == c2_id
    assert c1_phone == shared_phone

    # Clean up
    with postgres_app.app_context():
        b = db.session.get(Booking, book1_id)
        if b:
            db.session.delete(b)
        db.session.delete(db.session.get(AvailabilitySlot, slot_id))
        db.session.delete(db.session.get(LabTest, lab_test_id))
        db.session.delete(db.session.get(TestCategory, cat_id))
        db.session.delete(db.session.get(Branch, branch_id))
        cust = db.session.get(Customer, c1_id)
        if cust:
            db.session.delete(cust)
        db.session.commit()


def test_active_snapshot_session_integrity(postgres_app) -> None:
    """Verify session cannot adopt a snapshot created by a different conversation session (ORM and DB trigger)."""
    suffix = secrets.token_hex(4)
    sess_a_id = f"session-integrity-a-{suffix}"
    sess_b_id = f"session-integrity-b-{suffix}"
    with postgres_app.app_context():
        session_a = ConversationSession(session_id=sess_a_id, current_state={})
        session_b = ConversationSession(session_id=sess_b_id, current_state={})
        db.session.add_all([session_a, session_b])
        db.session.flush()

        snap_a = SearchSnapshot(
            session_id=sess_a_id,
            sequence_no=1,
            query="CBC",
            status="ACTIVE",
        )
        snap_b = SearchSnapshot(
            session_id=sess_b_id,
            sequence_no=1,
            query="Lipid",
            status="ACTIVE",
        )
        db.session.add_all([snap_a, snap_b])
        db.session.commit()

        # 1. ORM @validates layer rejection
        with pytest.raises(ValueError, match="Cross-session snapshot assignment rejected"):
            session_a.active_snapshot = snap_b

        # 2. Repository layer rejection
        repo = ConversationRepository()
        with pytest.raises(ValueError, match="Cross-session snapshot assignment rejected"):
            repo.set_active_snapshot(sess_a_id, snap_b.id)

        # 3. Database PostgreSQL trigger enforcement via raw SQL
        with pytest.raises((IntegrityError, ProgrammingError)):
            db.session.execute(
                text(
                    "UPDATE conversation_sessions "
                    "SET active_snapshot_id = :snap_id "
                    "WHERE session_id = :sess_id"
                ),
                {"snap_id": snap_b.id, "sess_id": sess_a_id},
            )
            db.session.commit()
        db.session.rollback()

        # 4. Valid assignment succeeds
        valid_sess = repo.set_active_snapshot(sess_a_id, snap_a.id)
        assert valid_sess.active_snapshot_id == snap_a.id

        # Clean up
        db.session.delete(session_a)
        db.session.delete(session_b)
        db.session.commit()


def test_find_available_slots_past_filter(postgres_app) -> None:
    """Verify BranchService.find_available_slots filters out past slots by default."""
    suffix = secrets.token_hex(4)
    with postgres_app.app_context():
        branch = Branch(
            name=f"Past Filter Branch {suffix}",
            address="Filter St",
            phone=f"+20109{suffix[:6]}",
            opening_hours_json={},
            active=True,
        )
        db.session.add(branch)
        db.session.flush()

        past_slot = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 9, 1),
            time=time(9, 0),
            capacity=2,
            reserved_count=0,
            active=True,
        )
        future_slot = AvailabilitySlot(
            branch_id=branch.id,
            visit_type="BRANCH",
            date=date(2026, 9, 25),
            time=time(9, 0),
            capacity=2,
            reserved_count=0,
            active=True,
        )
        db.session.add_all([past_slot, future_slot])
        db.session.commit()

        service = BranchService()

        # Default filtering with explicit from_date=2026-09-12 (simulating present date)
        slots = service.find_available_slots(
            visit_type="BRANCH",
            branch_id=branch.id,
            from_date=date(2026, 9, 12),
        )
        slot_dates = [s.date for s in slots]
        assert date(2026, 9, 25) in slot_dates
        assert date(2026, 9, 1) not in slot_dates

        # With include_past=True, past slot should be included
        all_slots = service.find_available_slots(
            visit_type="BRANCH",
            branch_id=branch.id,
            from_date=date(2026, 9, 12),
            include_past=True,
        )
        all_dates = [s.date for s in all_slots]
        assert date(2026, 9, 1) in all_dates
        assert date(2026, 9, 25) in all_dates

        # Clean up
        db.session.delete(past_slot)
        db.session.delete(future_slot)
        db.session.delete(branch)
        db.session.commit()


def test_seed_db_idempotency_on_postgres(postgres_app) -> None:
    """Verify seed_db.py runs idempotently on real PostgreSQL without duplicate violations."""
    with postgres_app.app_context():
        # First execution
        counts1 = run_seed()
        assert counts1["categories"] == 5
        assert counts1["lab_tests"] == 11
        assert counts1["packages"] == 3
        assert counts1["branches"] == 4
        assert counts1["knowledge_documents"] == 4
        assert counts1["availability_slots"] > 0

        # Second execution: must produce exact same counts
        counts2 = run_seed()
        assert counts2 == counts1
