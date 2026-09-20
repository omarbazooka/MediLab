"""Repository for Branch and AvailabilitySlot entities."""

from __future__ import annotations

from datetime import date, time

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
        from_date: date | None = None,
        include_past: bool = False,
        active_only: bool = True,
    ) -> list[AvailabilitySlot]:
        """Find slots with available capacity matching criteria.

        By default, excludes slots prior to from_date (or current date if unspecified)
        unless target_date is explicitly given or include_past is True.
        """
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
        elif not include_past:
            effective_from = from_date or date.today()
            stmt = stmt.where(AvailabilitySlot.date >= effective_from)

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

    def find_slot_by_date_time(
        self,
        target_date: date,
        target_time: time,
        branch_id: int | None = None,
        visit_type: str = "BRANCH",
        for_update: bool = False,
    ) -> AvailabilitySlot | None:
        """Fetch a specific slot by date, time, and branch or home visit pool."""
        stmt = (
            select(AvailabilitySlot)
            .where(
                AvailabilitySlot.date == target_date,
                AvailabilitySlot.time == target_time,
                AvailabilitySlot.visit_type == visit_type.strip().upper(),
            )
            .options(selectinload(AvailabilitySlot.branch))
        )
        if visit_type.strip().upper() == "BRANCH":
            stmt = stmt.where(AvailabilitySlot.branch_id == branch_id)
        else:
            stmt = stmt.where(AvailabilitySlot.branch_id.is_(None))

        if for_update:
            stmt = stmt.with_for_update()
        return db.session.execute(stmt).scalar_one_or_none()

    def find_nearby_available_slots(
        self,
        target_date: date,
        target_time: time,
        branch_id: int | None = None,
        visit_type: str = "BRANCH",
        limit: int = 3,
    ) -> list[AvailabilitySlot]:
        """Find real available slots on or near target_date closest to target_time."""
        clean_visit_type = visit_type.strip().upper()
        stmt = (
            select(AvailabilitySlot)
            .where(
                AvailabilitySlot.date == target_date,
                AvailabilitySlot.visit_type == clean_visit_type,
                AvailabilitySlot.active.is_(True),
                AvailabilitySlot.reserved_count < AvailabilitySlot.capacity,
            )
            .options(selectinload(AvailabilitySlot.branch))
        )
        if clean_visit_type == "BRANCH":
            if branch_id is not None:
                stmt = stmt.where(AvailabilitySlot.branch_id == branch_id)
        else:
            stmt = stmt.where(AvailabilitySlot.branch_id.is_(None))

        slots = list(db.session.execute(stmt).scalars().all())

        if not slots:
            # Fallback to next upcoming dates with availability
            stmt_fwd = (
                select(AvailabilitySlot)
                .where(
                    AvailabilitySlot.date > target_date,
                    AvailabilitySlot.visit_type == clean_visit_type,
                    AvailabilitySlot.active.is_(True),
                    AvailabilitySlot.reserved_count < AvailabilitySlot.capacity,
                )
                .options(selectinload(AvailabilitySlot.branch))
                .order_by(AvailabilitySlot.date, AvailabilitySlot.time)
                .limit(limit)
            )
            if clean_visit_type == "BRANCH" and branch_id is not None:
                stmt_fwd = stmt_fwd.where(AvailabilitySlot.branch_id == branch_id)
            elif clean_visit_type == "HOME":
                stmt_fwd = stmt_fwd.where(AvailabilitySlot.branch_id.is_(None))
            return list(db.session.execute(stmt_fwd).scalars().all())

        # Sort slots on target_date by proximity in minutes to target_time
        target_minutes = target_time.hour * 60 + target_time.minute
        slots.sort(key=lambda s: abs((s.time.hour * 60 + s.time.minute) - target_minutes))
        return slots[:limit]
