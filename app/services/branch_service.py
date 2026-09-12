"""Service for branch information and appointment availability search."""

from __future__ import annotations

from datetime import date

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
        active_only: bool = True,
    ) -> list[AvailabilitySlot]:
        """Query available slots with unreserved capacity."""
        return self.repository.find_available_slots(
            branch_id=branch_id,
            visit_type=visit_type,
            target_date=target_date,
            active_only=active_only,
        )
