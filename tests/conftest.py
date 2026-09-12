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
def postgres_app() -> Generator[Flask, None, None]:
    """Create an app bound to an explicitly configured real PostgreSQL database."""
    database_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for integration tests")

    app_db_url = os.getenv("DATABASE_URL", "").strip()
    validate_test_database_url(database_url, app_db_url)

    app_instance = create_app(
        "testing",
        test_config={"SQLALCHEMY_DATABASE_URI": database_url},
    )
    yield app_instance


@pytest.fixture
def postgres_client(postgres_app: Flask) -> FlaskClient:
    return postgres_app.test_client()
