"""Base model definitions and mixins for MediLab AI."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

# Multi-dialect type definitions: Native PostgreSQL in production, standard JSON/Text in SQLite unit tests
JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")
TSVECTOR_VARIANT = Text().with_variant(TSVECTOR, "postgresql")


class TimestampMixin:
    """Provides automatic UTC creation and update timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
