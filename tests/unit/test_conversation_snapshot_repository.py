"""Tests for visible SearchSnapshot lifecycle invariants."""

from __future__ import annotations

from flask import Flask

from app.extensions import db
from app.repositories.conversation_repository import ConversationRepository


def test_new_snapshot_stales_previous_active_snapshot(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        repo = ConversationRepository()
        repo.create_session("snapshot-life-1")

        first = repo.save_snapshot(
            session_id="snapshot-life-1",
            sequence_no=1,
            query="thyroid",
            criteria={"target": "test_selection"},
            items=[{"position": 1, "type": "test", "id": 1, "name": "TSH"}],
        )
        second = repo.save_snapshot(
            session_id="snapshot-life-1",
            sequence_no=1,
            query="wellness",
            criteria={"target": "package_selection"},
            items=[{"position": 1, "type": "package", "id": 2, "name": "Wellness"}],
        )
        db.session.commit()

        assert first.status == "STALE"
        assert second.status == "ACTIVE"
        assert second.sequence_no == 2
        session = repo.get_session("snapshot-life-1")
        assert session is not None
        assert session.active_snapshot_id == second.id
