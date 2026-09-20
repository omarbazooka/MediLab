"""Repository for Package entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.package import Package


class PackageRepository:
    """Data access repository for diagnostic packages and included tests."""

    def get_by_id(self, package_id: int) -> Package | None:
        """Fetch package by ID including bundled tests."""
        stmt = select(Package).where(Package.id == package_id).options(selectinload(Package.tests))
        return db.session.execute(stmt).scalar_one_or_none()

    def get_by_name(self, name: str) -> Package | None:
        """Fetch package by exact name (case-insensitive)."""
        stmt = (
            select(Package)
            .where(Package.name.ilike(name.strip()))
            .options(selectinload(Package.tests))
        )
        return db.session.execute(stmt).scalar_one_or_none()

    def search(self, query: str | None = None, active_only: bool = True) -> list[Package]:
        """Search packages by query string matching name or description."""
        stmt = select(Package).options(selectinload(Package.tests))

        if active_only:
            stmt = stmt.where(Package.active.is_(True))

        if query:
            clean_query = f"%{query.strip().lower()}%"
            stmt = stmt.where(
                (Package.name.ilike(clean_query)) | (Package.description.ilike(clean_query))
            )

        stmt = stmt.order_by(Package.name)
        results = list(db.session.execute(stmt).scalars().all())

        # If no results matched the full phrase, fallback to search across meaningful tokens
        if not results and query:
            stopwords = {
                "what",
                "which",
                "packages",
                "package",
                "offer",
                "have",
                "with",
                "for",
                "about",
                "your",
            }
            tokens = [
                w.strip().lower()
                for w in query.split()
                if len(w.strip()) >= 3 and w.strip().lower() not in stopwords
            ]
            if tokens:
                from sqlalchemy import or_

                token_stmt = select(Package).options(selectinload(Package.tests))
                if active_only:
                    token_stmt = token_stmt.where(Package.active.is_(True))
                conditions = []
                for token in tokens:
                    pat = f"%{token}%"
                    conditions.append(Package.name.ilike(pat) | Package.description.ilike(pat))
                token_stmt = token_stmt.where(or_(*conditions)).order_by(Package.name)
                results = list(db.session.execute(token_stmt).scalars().all())

        return results
