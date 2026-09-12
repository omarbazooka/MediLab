"""Repository for ConversationSession, ChatMessage, and SearchSnapshot entities."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.conversation import ChatMessage, ConversationSession
from app.models.snapshot import SearchSnapshot


class ConversationRepository:
    """Data access repository for conversation state and visible search snapshots."""

    def get_session(self, session_id: str) -> ConversationSession | None:
        """Fetch conversation session by external session identifier."""
        stmt = (
            select(ConversationSession)
            .where(ConversationSession.session_id == session_id)
            .options(
                selectinload(ConversationSession.messages),
                selectinload(ConversationSession.snapshots),
                selectinload(ConversationSession.active_snapshot),
            )
        )
        return db.session.execute(stmt).scalar_one_or_none()

    def create_session(
        self,
        session_id: str,
        customer_id: int | None = None,
        initial_state: dict[str, Any] | None = None,
    ) -> ConversationSession:
        """Create and persist a new conversation session."""
        session = ConversationSession(
            session_id=session_id,
            customer_id=customer_id,
            current_state=initial_state or {},
        )
        db.session.add(session)
        db.session.flush()
        return session

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        metadata_: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """Append a message to an existing conversation session."""
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
            metadata_=metadata_ or {},
        )
        db.session.add(message)
        db.session.flush()
        return message

    def save_snapshot(
        self,
        session_id: str,
        sequence_no: int,
        query: str,
        criteria: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> SearchSnapshot:
        """Persist a search snapshot with strict visible sequence ordering."""
        snapshot = SearchSnapshot(
            session_id=session_id,
            sequence_no=sequence_no,
            query=query,
            criteria=criteria,
            items=items,
        )
        db.session.add(snapshot)
        db.session.flush()

        # Update session's active_snapshot_id
        session = self.get_session(session_id)
        if session:
            session.active_snapshot_id = snapshot.id
            db.session.flush()

        return snapshot

    def get_latest_snapshot(self, session_id: str) -> SearchSnapshot | None:
        """Fetch the most recent search snapshot for a given conversation session."""
        stmt = (
            select(SearchSnapshot)
            .where(SearchSnapshot.session_id == session_id)
            .order_by(SearchSnapshot.sequence_no.desc())
        )
        return db.session.execute(stmt).scalars().first()

    def set_active_snapshot(self, session_id: str, snapshot_id: int) -> ConversationSession:
        """Set the active snapshot for a session with strict cross-session ownership verification."""
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found.")

        snapshot = db.session.get(SearchSnapshot, snapshot_id)
        if snapshot is None:
            raise ValueError(f"Snapshot with ID {snapshot_id} not found.")

        if snapshot.session_id != session_id:
            raise ValueError(
                f"Cross-session snapshot assignment rejected: Snapshot {snapshot_id} belongs to "
                f"session '{snapshot.session_id}', not '{session_id}'."
            )

        session.active_snapshot_id = snapshot.id
        db.session.flush()
        return session
