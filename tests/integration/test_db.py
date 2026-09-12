"""Real PostgreSQL and pgvector integration tests."""

from __future__ import annotations

import pytest
from flask import Flask
from sqlalchemy import text

from app.extensions import db

pytestmark = pytest.mark.postgres


def test_postgresql_connection(postgres_app: Flask) -> None:
    with postgres_app.app_context(), db.engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
        assert connection.execute(text("SELECT current_database()")).scalar_one()


def test_pgvector_available_and_functional(postgres_app: Flask) -> None:
    with postgres_app.app_context(), db.engine.begin() as connection:
        available_version = connection.execute(
            text(
                "SELECT default_version FROM pg_available_extensions "
                "WHERE name = 'vector'"
            )
        ).scalar_one_or_none()
        assert available_version is not None, "pgvector is not available in PostgreSQL"

        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        installed_version = connection.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
        assert installed_version is not None

        vector_value = connection.execute(text("SELECT '[1,2,3]'::vector::text")).scalar_one()
        assert vector_value == "[1,2,3]"
