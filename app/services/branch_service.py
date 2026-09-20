"""Service for branch information and appointment availability search."""

from __future__ import annotations

from datetime import date, time

from app.models.branch import AvailabilitySlot, Branch
from app.repositories.branch_repository import BranchRepository


class BranchService:
    """Business service for physical branches and available appointment slots."""

    def __init__(self, repository: BranchRepository | None = None) -> None:
        self.repository = repository or BranchRepository()

    def list_active_branches(self) -> list[Branch]:
        """List all active laboratory branches."""
        return self.repository.list_active_branches()

    def get_branch_details(self, branch_id: int) -> Branch | None:
        """Fetch details for a specific branch."""
        return self.repository.get_by_id(branch_id)

    def find_available_slots(
        self,
        branch_id: int | None = None,
        visit_type: str | None = None,
        target_date: date | None = None,
        from_date: date | None = None,
        include_past: bool = False,
        active_only: bool = True,
    ) -> list[AvailabilitySlot]:
        """Query available slots with unreserved capacity, excluding past slots by default."""
        return self.repository.find_available_slots(
            branch_id=branch_id,
            visit_type=visit_type,
            target_date=target_date,
            from_date=from_date,
            include_past=include_past,
            active_only=active_only,
        )

    def find_slot_by_date_time(
        self,
        target_date: date,
        target_time: time,
        branch_id: int | None = None,
        visit_type: str = "BRANCH",
    ) -> AvailabilitySlot | None:
        """Fetch a specific slot by date, time, and branch or home visit pool."""
        return self.repository.find_slot_by_date_time(
            target_date=target_date,
            target_time=target_time,
            branch_id=branch_id,
            visit_type=visit_type,
        )

    def find_nearby_available_slots(
        self,
        target_date: date,
        target_time: time,
        branch_id: int | None = None,
        visit_type: str = "BRANCH",
        limit: int = 3,
    ) -> list[AvailabilitySlot]:
        """Query real available alternative slots closest to target_time."""
        return self.repository.find_nearby_available_slots(
            target_date=target_date,
            target_time=target_time,
            branch_id=branch_id,
            visit_type=visit_type,
            limit=limit,
        )
