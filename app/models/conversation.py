"""ConversationSession and ChatMessage models for conversation context persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSON_VARIANT, TimestampMixin

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.package import Package
    from app.models.snapshot import SearchSnapshot
    from app.models.test import LabTest


class ConversationSession(TimestampMixin, db.Model):
    """Persistent multi-turn conversation session."""

    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    selected_test_id: Mapped[int | None] = mapped_column(
        ForeignKey("lab_tests.id", ondelete="SET NULL"),
        nullable=True,
    )
    selected_package_id: Mapped[int | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_state: Mapped[dict[str, Any]] = mapped_column(
        JSON_VARIANT, default=dict, nullable=False
    )
    pending_action: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT, nullable=True)
    pending_clarification: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_VARIANT, nullable=True
    )

    # Resolves circular FK between SearchSnapshot.session_id and active_snapshot_id
    active_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "search_snapshots.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_conversation_sessions_active_snapshot_id",
        ),
        nullable=True,
    )

    customer: Mapped[Customer | None] = relationship("Customer")
    selected_test: Mapped[LabTest | None] = relationship("LabTest")
    selected_package: Mapped[Package | None] = relationship("Package")
    active_snapshot: Mapped[SearchSnapshot | None] = relationship(
        "SearchSnapshot",
        foreign_keys=[active_snapshot_id],
        post_update=True,
    )
    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )
    snapshots: Mapped[list[SearchSnapshot]] = relationship(
        "SearchSnapshot",
        foreign_keys="SearchSnapshot.session_id",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SearchSnapshot.sequence_no",
    )

    def __repr__(self) -> str:
        return f"<ConversationSession id={self.id} session_id='{self.session_id}'>"


class ChatMessage(db.Model):
    """Individual message in a conversation thread."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_chat_messages_role"),
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON_VARIANT,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    session: Mapped[ConversationSession] = relationship(
        "ConversationSession", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} session='{self.session_id}' role='{self.role}'>"
