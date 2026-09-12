"""Unit tests verifying the test database isolation safety guard."""

from __future__ import annotations

import pytest

from tests.conftest import validate_test_database_url


def test_safety_guard_blocks_supabase_url() -> None:
    """Ensure safety guard rejects any cloud/Supabase database URL for test runs."""
    supabase_url = (
        "postgresql+psycopg://postgres:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
    )
    with pytest.raises(
        RuntimeError,
        match="SAFETY VIOLATION: TEST_DATABASE_URL points to a cloud/Supabase database",
    ):
        validate_test_database_url(
            supabase_url, "postgresql+psycopg://postgres:secret@localhost:5432/medilab"
        )


def test_safety_guard_blocks_identical_db_url() -> None:
    """Ensure safety guard rejects identical test and application database URLs."""
    local_url = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab_prod"
    with pytest.raises(
        RuntimeError,
        match="SAFETY VIOLATION: TEST_DATABASE_URL targets the production/application database",
    ):
        validate_test_database_url(local_url, local_url)


def test_safety_guard_allows_disposable_local_url() -> None:
    """Ensure safety guard allows distinct disposable local test database."""
    test_url = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab_test"
    app_url = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab_prod"
    # Should not raise
    validate_test_database_url(test_url, app_url)
