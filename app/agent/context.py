"""Durable conversation context loading and customer history hydration."""

from __future__ import annotations

from typing import Any

from app.repositories.conversation_repository import ConversationRepository
from app.services.customer_context_service import CustomerContextService


def load_conversation_context(
    session_id: str,
    max_messages: int = 10,
    max_customer_bookings: int = 5,
    conversation_repo: ConversationRepository | None = None,
    customer_service: CustomerContextService | None = None,
) -> dict[str, Any]:
    """Load bounded durable conversation state, messages, and customer history from PostgreSQL."""
    repo = conversation_repo or ConversationRepository()
    cust_service = customer_service or CustomerContextService()

    session = repo.get_session(session_id)
    if session is None:
        session = repo.create_session(session_id=session_id)

    # Bounded recent messages in chronological order.
    all_msgs = session.messages or []
    bounded_msgs = all_msgs[-max_messages:] if len(all_msgs) > max_messages else all_msgs
    formatted_msgs = [
        {
            "role": m.role,
            "content": m.content,
            "intent": m.intent,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in bounded_msgs
    ]

    # Only the session's explicitly ACTIVE snapshot can back visible references.
    snapshot_data: dict[str, Any] | None = None
    if session.active_snapshot and session.active_snapshot.status == "ACTIVE":
        snap = session.active_snapshot
        snapshot_data = {
            "id": snap.id,
            "sequence_no": snap.sequence_no,
            "query": snap.query,
            "status": snap.status,
            "items": snap.items,
        }

    customer_context = None
    if session.customer_id:
        customer_context = cust_service.get_customer_context(
            session.customer_id,
            max_bookings=max_customer_bookings,
        )

    return {
        "session_id": session.session_id,
        "customer_id": session.customer_id,
        "recent_messages": formatted_msgs,
        "current_state": session.current_state or {},
        "selected_test_id": session.selected_test_id,
        "selected_test_code": session.selected_test.code if session.selected_test else None,
        "selected_test_name": session.selected_test.name if session.selected_test else None,
        "selected_package_id": session.selected_package_id,
        "selected_package_name": session.selected_package.name
        if session.selected_package
        else None,
        "active_search_snapshot": snapshot_data,
        "pending_clarification": session.pending_clarification,
        "pending_action": session.pending_action,
        "customer_context": customer_context,
    }
