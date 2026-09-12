"""Repository for LabTest and TestCategory entities."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.test import LabTest, TestCategory


class TestRepository:
    """Data access repository for diagnostic tests and categories."""

    def get_by_id(self, test_id: int) -> LabTest | None:
        """Fetch a single test by its primary key ID."""
        stmt = (
            select(LabTest)
            .where(LabTest.id == test_id)
            .options(selectinload(LabTest.category), selectinload(LabTest.packages))
        )
        return db.session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> LabTest | None:
        """Fetch a single test by its unique code (case-insensitive)."""
        normalized_code = code.strip().upper()
        stmt = (
            select(LabTest)
            .where(LabTest.code == normalized_code)
            .options(selectinload(LabTest.category), selectinload(LabTest.packages))
        )
        return db.session.execute(stmt).scalar_one_or_none()

    def search(
        self,
        query: str | None = None,
        category_id: int | None = None,
        category_slug: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        active_only: bool = True,
    ) -> list[LabTest]:
        """Perform structured search across catalog tests with optional filters."""
        stmt = select(LabTest).options(selectinload(LabTest.category))

        if active_only:
            stmt = stmt.where(LabTest.active.is_(True))

        if category_id is not None:
            stmt = stmt.where(LabTest.category_id == category_id)

        if category_slug is not None:
            stmt = stmt.join(LabTest.category).where(
                TestCategory.slug == category_slug.strip().lower()
            )

        if min_price is not None:
            stmt = stmt.where(LabTest.price >= min_price)

        if max_price is not None:
            stmt = stmt.where(LabTest.price <= max_price)

        if query:
            clean_query = f"%{query.strip().lower()}%"
            stmt = stmt.where((LabTest.code.ilike(clean_query)) | (LabTest.name.ilike(clean_query)))

        stmt = stmt.order_by(LabTest.name)
        return list(db.session.execute(stmt).scalars().all())

    def list_categories(self, active_only: bool = True) -> list[TestCategory]:
        """Return all test categories ordered by name."""
        stmt = select(TestCategory)
        if active_only:
            stmt = stmt.where(TestCategory.active.is_(True))
        stmt = stmt.order_by(TestCategory.name)
        return list(db.session.execute(stmt).scalars().all())

    def get_category_by_slug(self, slug: str) -> TestCategory | None:
        """Fetch category by its unique slug."""
        stmt = select(TestCategory).where(TestCategory.slug == slug.strip().lower())
        return db.session.execute(stmt).scalar_one_or_none()
