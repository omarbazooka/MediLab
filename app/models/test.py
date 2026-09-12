"""TestCategory and LabTest models for diagnostic catalog."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.package import Package


class TestCategory(TimestampMixin, db.Model):
    """Categorization for laboratory tests (e.g. Hematology, Biochemistry)."""

    __test__ = False

    __tablename__ = "test_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    tests: Mapped[list[LabTest]] = relationship(
        "LabTest",
        back_populates="category",
        order_by="LabTest.name",
    )

    def __repr__(self) -> str:
        return f"<TestCategory id={self.id} slug='{self.slug}'>"


class LabTest(TimestampMixin, db.Model):
    """Individual laboratory diagnostic test."""

    __tablename__ = "lab_tests"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_lab_tests_price_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("test_categories.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    sample_type: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    result_turnaround_text: Mapped[str] = mapped_column(String(150), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    category: Mapped[TestCategory] = relationship("TestCategory", back_populates="tests")
    packages: Mapped[list[Package]] = relationship(
        "Package",
        secondary="package_tests",
        back_populates="tests",
    )

    def __repr__(self) -> str:
        return f"<LabTest id={self.id} code='{self.code}' name='{self.name}'>"
