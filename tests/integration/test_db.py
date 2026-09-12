"""Integration tests for database connectivity and pgvector extension support."""

import os

import pytest
from flask import Flask
from sqlalchemy import text

from app.extensions import db


def test_database_connection_probe(app: Flask) -> None:
    """The database session should be able to execute a simple probe query."""
    with app.app_context():
        result = db.session.execute(text("SELECT 1")).scalar()
        assert result == 1


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL not active in current test environment; pgvector test requires PostgreSQL",
)
def test_pgvector_extension_installed(app: Flask) -> None:
    """PostgreSQL database should have the pgvector extension installed and functional."""
    with app.app_context():
        # Check pgvector extension registration
        result = db.session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        assert result == "vector", "The 'vector' extension is not installed in PostgreSQL."

        # Verify pgvector vector data type functionality
        vector_test = db.session.execute(text("SELECT '[1,2,3]'::vector")).scalar()
        assert vector_test is not None
