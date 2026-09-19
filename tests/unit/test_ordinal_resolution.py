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
    """Resolve 'the second one' deterministically to visible position 2."""
    with app.app_context():
        state = create_initial_state("sess-ord-1", "I will take the second one")
        state["active_search_snapshot"] = {
            "id": 10,
            "status": "ACTIVE",
            "items": [
                {"position": 1, "type": "test", "id": 101, "code": "TSH", "name": "TSH"},
                {"position": 2, "type": "package", "id": 202, "name": "Vitality & Wellness Panel"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}

        update = resolve_pending_context(state)

        assert update["selected_package_id"] == 202
        assert update["selected_test_id"] is None
        assert update["pending_clarification"] is None
        assert update["needs_clarification"] is False


def test_ordinal_resolution_arabic_altany(app: Flask) -> None:
    """Resolve 'التاني' in Arabic to the second visible item."""
    with app.app_context():
        state = create_initial_state("sess-ord-2", "عايز التاني")
        state["active_search_snapshot"] = {
            "id": 11,
            "status": "ACTIVE",
            "items": [
                {"position": 1, "type": "test", "id": 50, "code": "CBC", "name": "CBC"},
                {"position": 2, "type": "test", "id": 51, "code": "FERRITIN", "name": "Ferritin"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}

        update = resolve_pending_context(state)

        assert update["selected_test_id"] == 51
        assert update["pending_clarification"] is None


def test_ordinal_resolution_the_full_one(app: Flask) -> None:
    """Resolve semantic follow-up only after LLM proposes a visible package."""
    with app.app_context():
        state = create_initial_state("sess-ord-3", "The full one please")
        state["active_search_snapshot"] = {
            "id": 12,
            "status": "ACTIVE",
            "items": [
                {"position": 1, "type": "test", "id": 1, "code": "TSH", "name": "Thyroid Stimulating Hormone"},
                {"position": 2, "type": "package", "id": 3, "name": "Vitality & Wellness Panel"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}
        state["entities"] = {"visible_item_id": 3, "visible_item_type": "package"}

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


def test_stale_snapshot_cannot_resolve_ordinal(app: Flask) -> None:
    """A stale snapshot must never back a visible positional reference."""
    with app.app_context():
        state = create_initial_state("sess-ord-stale", "the second one")
        state["active_search_snapshot"] = {
            "id": 19,
            "status": "STALE",
            "items": [
                {"position": 1, "type": "test", "id": 1, "name": "TSH"},
                {"position": 2, "type": "package", "id": 3, "name": "Wellness Panel"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}
        state["needs_clarification"] = True

        update = resolve_pending_context(state)

        assert update["selected_test_id"] is None
        assert update["selected_package_id"] is None
        assert update["needs_clarification"] is True
        assert update["pending_clarification"] is not None


def test_the_full_option_cannot_escape_snapshot_when_only_tests_visible(app: Flask) -> None:
    """A semantic reference cannot select a package absent from the visible snapshot."""
    with app.app_context():
        state = create_initial_state("sess-ord-5", "I mean the full option")
        state["active_search_snapshot"] = {
            "id": 15,
            "status": "ACTIVE",
            "items": [
                {"position": 1, "type": "test", "id": 101, "code": "TSH", "name": "TSH"},
                {"position": 2, "type": "test", "id": 102, "code": "FT3", "name": "Free T3"},
                {"position": 3, "type": "test", "id": 103, "code": "FT4", "name": "Free T4"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}
        state["needs_clarification"] = True
        state["entities"] = {"visible_item_id": 999, "visible_item_type": "package"}

        update = resolve_pending_context(state)

        assert update["selected_package_id"] is None
        assert update["selected_test_id"] is None
        assert update["needs_clarification"] is True
        assert update["pending_clarification"] is not None


def test_the_full_option_arabic_with_visible_package(app: Flask) -> None:
    """Arabic semantic follow-up resolves only to an LLM-proposed visible package."""
    with app.app_context():
        state = create_initial_state("sess-ord-6", "أقصد الباقة الكاملة")
        state["active_search_snapshot"] = {
            "id": 16,
            "status": "ACTIVE",
            "items": [
                {"position": 1, "type": "test", "id": 1, "code": "TSH", "name": "TSH"},
                {"position": 2, "type": "package", "id": 88, "name": "باقة الفحص الشامل"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}
        state["needs_clarification"] = True
        state["entities"] = {"visible_item_id": 88, "visible_item_type": "package"}

        update = resolve_pending_context(state)

        assert update["selected_package_id"] == 88
        assert update["selected_test_id"] is None
        assert update["needs_clarification"] is False
        assert update["pending_clarification"] is None


def test_ordinal_out_of_bounds_does_not_select(app: Flask) -> None:
    """Selecting 4th option when only 2 are visible must not select anything."""
    with app.app_context():
        state = create_initial_state("sess-ord-7", "الرابع")
        state["active_search_snapshot"] = {
            "id": 17,
            "status": "ACTIVE",
            "items": [
                {"position": 1, "type": "test", "id": 1, "code": "TSH", "name": "TSH"},
                {"position": 2, "type": "test", "id": 2, "code": "CBC", "name": "CBC"},
            ],
        }
        state["pending_clarification"] = {"target": "test_selection", "attempts": 1}
        state["needs_clarification"] = True

        update = resolve_pending_context(state)

        assert update["selected_test_id"] is None
        assert update["selected_package_id"] is None
        assert update["needs_clarification"] is True
