"""Shared pytest fixtures for MediLab AI."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from flask import Flask
from flask.testing import FlaskClient

from app import create_app

load_dotenv()

_POSTGRES_REACHABLE: dict[str, bool] = {}


@pytest.fixture
def app() -> Flask:
    """Create a fast isolated application for unit-level HTTP tests."""
    return create_app(
        "testing",
        test_config={"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"},
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def validate_test_database_url(test_db_url: str, app_db_url: str | None = None) -> None:
    """Safety guard ensuring test database is strictly isolated and never targets Supabase/app DB."""
    from urllib.parse import urlparse

    if not test_db_url.startswith(("postgresql://", "postgresql+psycopg://")):
        return

    test_parsed = urlparse(test_db_url.replace("postgresql+psycopg://", "postgresql://"))
    if test_parsed.hostname and (
        "supabase" in test_parsed.hostname or "supabase.co" in test_parsed.hostname
    ):
        raise RuntimeError(
            "SAFETY VIOLATION: TEST_DATABASE_URL points to a cloud/Supabase database! "
            "Integration and destructive tests must ONLY run on disposable local/Docker PostgreSQL."
        )

    if app_db_url:
        app_parsed = urlparse(app_db_url.replace("postgresql+psycopg://", "postgresql://"))
        same_host = test_parsed.hostname and test_parsed.hostname == app_parsed.hostname
        same_path = test_parsed.path and test_parsed.path == app_parsed.path
        if test_db_url == app_db_url or (same_host and same_path):
            raise RuntimeError(
                "SAFETY VIOLATION: TEST_DATABASE_URL targets the production/application database! "
                "Integration and destructive tests must NEVER target the application database."
            )


@pytest.fixture
def postgres_app(request: pytest.FixtureRequest) -> Generator[Flask, None, None]:
    """Create an app bound to an explicitly configured real PostgreSQL database."""
    database_url = os.getenv("TEST_DATABASE_URL", "").strip()
    is_explicit_postgres_run = "postgres" in (request.config.getoption("-m") or "")

    if not database_url:
        if is_explicit_postgres_run:
            pytest.fail(
                "TEST_DATABASE_URL is not configured but postgres tests were explicitly requested."
            )
        pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for integration tests")

    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail(
            f"TEST_DATABASE_URL must be a PostgreSQL connection string, got: {database_url[:15]}..."
        )

    app_db_url = os.getenv("DATABASE_URL", "").strip()
    validate_test_database_url(database_url, app_db_url)

    import socket
    from urllib.parse import urlparse

    parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://"))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    cache_key = f"{host}:{port}"
    if cache_key in _POSTGRES_REACHABLE:
        if not _POSTGRES_REACHABLE[cache_key]:
            pytest.fail(
                f"Configured TEST_DATABASE_URL at {cache_key} is unreachable. Ensure local Docker PostgreSQL is running."
            )
    else:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                _POSTGRES_REACHABLE[cache_key] = True
        except (OSError, TimeoutError):
            _POSTGRES_REACHABLE[cache_key] = False
            pytest.fail(
                f"Configured TEST_DATABASE_URL at {cache_key} is unreachable. Ensure local Docker PostgreSQL is running."
            )

    app_instance = create_app(
        "testing",
        test_config={"SQLALCHEMY_DATABASE_URI": database_url},
    )
    yield app_instance


@pytest.fixture
def postgres_client(postgres_app: Flask) -> FlaskClient:
    return postgres_app.test_client()
