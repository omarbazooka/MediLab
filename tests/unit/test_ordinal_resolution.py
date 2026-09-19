"""Unit tests for SearchSnapshot ordinal reference resolution."""

from __future__ import annotations

import pytest
from flask import Flask

from app.agent.nodes.resolve_pending_context import resolve_pending_context
from app.agent.state import create_initial_state
from app.extensions import db


@pytest.fixture(autouse=True)
def setup_db(app: Flask):
    with app.app_context():
        db.create_all()


def test_ordinal_resolution_second_item_english(app: Flask) -> None:
    """Resolve 'the second one' deterministically to items[1] in visible snapshot."""
    with app.app_context():
        state = create_initial_state("sess-ord-1", "I will take the second one")
        state["active_search_snapshot"] = {
            "id": 10,
            "items": [
                {"type": "test", "id": 101, "code": "TSH", "name": "TSH"},
                {"type": "package", "id": 202, "name": "Vitality & Wellness Panel"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}

        update = resolve_pending_context(state)

        assert update["selected_package_id"] == 202
        assert update["selected_test_id"] is None
        assert update["pending_clarification"] is None
        assert update["needs_clarification"] is False


def test_ordinal_resolution_arabic_altany(app: Flask) -> None:
    """Resolve 'التاني' in Arabic to the second item in visible snapshot."""
    with app.app_context():
        state = create_initial_state("sess-ord-2", "عايز التاني")
        state["active_search_snapshot"] = {
            "id": 11,
            "items": [
                {"type": "test", "id": 50, "code": "CBC", "name": "CBC"},
                {"type": "test", "id": 51, "code": "FERRITIN", "name": "Ferritin"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}

        update = resolve_pending_context(state)

        assert update["selected_test_id"] == 51
        assert update["pending_clarification"] is None


def test_ordinal_resolution_the_full_one(app: Flask) -> None:
    """Resolve 'the full one' to the multi-test panel package in visible snapshot."""
    with app.app_context():
        state = create_initial_state("sess-ord-3", "The full one please")
        state["active_search_snapshot"] = {
            "id": 12,
            "items": [
                {"type": "test", "id": 1, "code": "TSH", "name": "Thyroid Stimulating Hormone"},
                {"type": "package", "id": 3, "name": "Vitality & Wellness Panel"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}

        update = resolve_pending_context(state)

        assert update["selected_package_id"] == 3
        assert update["pending_clarification"] is None


def test_ordinal_resolution_without_snapshot_does_not_guess(app: Flask) -> None:
    """If no active snapshot exists, ordinal cannot resolve to a hidden database row."""
    with app.app_context():
        state = create_initial_state("sess-ord-4", "the second one")
        state["active_search_snapshot"] = None
        state["pending_clarification"] = None

        update = resolve_pending_context(state)

        assert update["selected_test_id"] is None
        assert update["selected_package_id"] is None
