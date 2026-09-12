"""Package and PackageTest models for multi-test packages."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.test import LabTest


class PackageTest(db.Model):
    """Association linking LabTests included in a Package."""

    __tablename__ = "package_tests"
    __table_args__ = (
        UniqueConstraint("package_id", "test_id", name="uq_package_tests_package_test"),
    )

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    test_id: Mapped[int] = mapped_column(
        ForeignKey("lab_tests.id", ondelete="CASCADE"),
        primary_key=True,
    )

    def __repr__(self) -> str:
        return f"<PackageTest package_id={self.package_id} test_id={self.test_id}>"


class Package(TimestampMixin, db.Model):
    """Diagnostic package containing multiple bundled tests at a bundled price."""

    __tablename__ = "packages"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_packages_price_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)

    tests: Mapped[list[LabTest]] = relationship(
        "LabTest",
        secondary="package_tests",
        back_populates="packages",
        order_by="LabTest.name",
    )

    def __repr__(self) -> str:
        return f"<Package id={self.id} name='{self.name}' price={self.price}>"
