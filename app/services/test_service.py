"""Service providing deterministic search and details for laboratory tests."""

from __future__ import annotations

from decimal import Decimal

from app.models.test import LabTest, TestCategory
from app.repositories.test_repository import TestRepository


class TestService:
    """Business service for querying diagnostic tests and categories."""

    __test__ = False

    def __init__(self, repository: TestRepository | None = None) -> None:
        self.repository = repository or TestRepository()

    def search_tests(
        self,
        query: str | None = None,
        category_id: int | None = None,
        category_slug: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        active_only: bool = True,
    ) -> list[LabTest]:
        """Search catalog tests matching code, name, category, or price range."""
        return self.repository.search(
            query=query,
            category_id=category_id,
            category_slug=category_slug,
            min_price=min_price,
            max_price=max_price,
            active_only=active_only,
        )

    def get_test_by_code(self, code: str) -> LabTest | None:
        """Retrieve single diagnostic test by its unique catalog code."""
        if not code or not code.strip():
            return None
        return self.repository.get_by_code(code)

    def get_test_details(self, test_id: int) -> LabTest | None:
        """Retrieve test details by ID."""
        return self.repository.get_by_id(test_id)

    def list_categories(self, active_only: bool = True) -> list[TestCategory]:
        """List all test categories."""
        return self.repository.list_categories(active_only=active_only)
