"""Unit tests for the Flask application factory and request middleware."""

from __future__ import annotations

import re

from flask import Flask

from app import create_app
from app.extensions import db, migrate


def test_create_app_testing_environment() -> None:
    app = create_app("testing")

    assert isinstance(app, Flask)
    assert app.config["TESTING"] is True
    assert app.config["DEBUG"] is False
    assert app.config["APP_ENV"] == "testing"
    assert "health" in app.blueprints


def test_create_app_with_test_overrides() -> None:
    app = create_app("testing", test_config={"CUSTOM_OVERRIDE": "test-value"})
    assert app.config["CUSTOM_OVERRIDE"] == "test-value"


def test_extensions_initialized() -> None:
    app = create_app("testing")
    assert "sqlalchemy" in app.extensions
    assert "migrate" in app.extensions
    with app.app_context():
        assert db.engine is not None
    assert migrate.db is db


def test_request_id_is_generated(client) -> None:
    response = client.get("/health")
    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)


def test_safe_request_id_is_preserved(client) -> None:
    custom_id = "frontend:request-123.abc"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.headers["X-Request-ID"] == custom_id


def test_unsafe_or_oversized_request_id_is_replaced(client) -> None:
    response = client.get("/health", headers={"X-Request-ID": "x" * 512})
    request_id = response.headers["X-Request-ID"]
    assert request_id != "x" * 512
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
