"""Repository for Branch and AvailabilitySlot entities."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.branch import AvailabilitySlot, Branch


class BranchRepository:
    """Data access repository for physical branches and appointment slots."""

    def list_active_branches(self) -> list[Branch]:
        """Return all active branches ordered by name."""
        stmt = select(Branch).where(Branch.active.is_(True)).order_by(Branch.name)
        return list(db.session.execute(stmt).scalars().all())

    def get_by_id(self, branch_id: int) -> Branch | None:
        """Fetch branch by primary key ID."""
        stmt = select(Branch).where(Branch.id == branch_id)
        return db.session.execute(stmt).scalar_one_or_none()

    def find_available_slots(
        self,
        branch_id: int | None = None,
        visit_type: str | None = None,
        target_date: date | None = None,
        active_only: bool = True,
    ) -> list[AvailabilitySlot]:
        """Find slots with available capacity matching criteria."""
        stmt = select(AvailabilitySlot).options(selectinload(AvailabilitySlot.branch))

        if active_only:
            stmt = stmt.where(AvailabilitySlot.active.is_(True))

        # Enforce that remaining capacity exists
        stmt = stmt.where(AvailabilitySlot.reserved_count < AvailabilitySlot.capacity)

        if branch_id is not None:
            stmt = stmt.where(AvailabilitySlot.branch_id == branch_id)

        if visit_type is not None:
            stmt = stmt.where(AvailabilitySlot.visit_type == visit_type.strip().upper())

        if target_date is not None:
            stmt = stmt.where(AvailabilitySlot.date == target_date)

        stmt = stmt.order_by(AvailabilitySlot.date, AvailabilitySlot.time)
        return list(db.session.execute(stmt).scalars().all())

    def get_slot_by_id(self, slot_id: int, for_update: bool = False) -> AvailabilitySlot | None:
        """Fetch a specific slot, optionally locking the row for transactional reservation."""
        stmt = (
            select(AvailabilitySlot)
            .where(AvailabilitySlot.id == slot_id)
            .options(selectinload(AvailabilitySlot.branch))
        )
        if for_update:
            stmt = stmt.with_for_update()
        return db.session.execute(stmt).scalar_one_or_none()
