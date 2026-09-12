"""Service providing diagnostic package search and details."""

from __future__ import annotations

from app.models.package import Package
from app.repositories.package_repository import PackageRepository


class PackageService:
    """Business service for diagnostic package catalog operations."""

    def __init__(self, repository: PackageRepository | None = None) -> None:
        self.repository = repository or PackageRepository()

    def search_packages(self, query: str | None = None, active_only: bool = True) -> list[Package]:
        """Search packages by name or description."""
        return self.repository.search(query=query, active_only=active_only)

    def get_package_details(self, package_id: int) -> Package | None:
        """Fetch package details along with bundled tests."""
        return self.repository.get_by_id(package_id)

    def get_package_by_name(self, name: str) -> Package | None:
        """Fetch package by exact name."""
        if not name or not name.strip():
            return None
        return self.repository.get_by_name(name)
