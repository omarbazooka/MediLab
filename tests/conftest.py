"""Shared pytest fixtures for MediLab AI."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app


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


@pytest.fixture
def postgres_app() -> Generator[Flask, None, None]:
    """Create an app bound to an explicitly configured real PostgreSQL database."""
    database_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for integration tests")

    app_instance = create_app(
        "testing",
        test_config={"SQLALCHEMY_DATABASE_URI": database_url},
    )
    yield app_instance


@pytest.fixture
def postgres_client(postgres_app: Flask) -> FlaskClient:
    return postgres_app.test_client()
