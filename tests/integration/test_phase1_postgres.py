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

from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.branch import AvailabilitySlot, Branch
from app.models.conversation import ConversationSession
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.package import Package, PackageTest
from app.models.snapshot import SearchSnapshot
from app.models.test import LabTest, TestCategory
from app.services.booking_service import (
    BookingService,
    BookingValidationError,
    CapacityExceededError,
)
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
