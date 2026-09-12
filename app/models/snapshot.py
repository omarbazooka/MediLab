"""SearchSnapshot model for tracking visible search results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSON_VARIANT

if TYPE_CHECKING:
    from app.models.conversation import ConversationSession


class SearchSnapshot(db.Model):
    """Snapshot of search results presented to the customer to support ordinal references."""

    __tablename__ = "search_snapshots"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_no", name="uq_search_snapshots_session_seq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, default=dict, nullable=False)
    # Critical: list of item references in the exact visual sequence presented to the user
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VARIANT, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    session: Mapped[ConversationSession] = relationship(
        "ConversationSession",
        foreign_keys=[session_id],
        back_populates="snapshots",
    )

    def __repr__(self) -> str:
        return (
            f"<SearchSnapshot id={self.id} session='{self.session_id}' "
            f"seq={self.sequence_no} items_count={len(self.items)}>"
        )
