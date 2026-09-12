"""Unit tests for Flask application factory."""

from flask import Flask

from app import create_app
from app.extensions import db, migrate


def test_create_app_testing_environment() -> None:
    """Application factory should initialize Flask app with TestingConfig."""
    app = create_app("testing")
    assert isinstance(app, Flask)
    assert app.config["TESTING"] is True
    assert app.config["DEBUG"] is False
    assert "health" in app.blueprints


def test_create_app_with_test_overrides() -> None:
    """Application factory should accept and apply test configuration overrides."""
    app = create_app(
        "testing",
        test_config={
            "CUSTOM_OVERRIDE": "test_value_123",
        },
    )
    assert app.config["CUSTOM_OVERRIDE"] == "test_value_123"


def test_extensions_initialized() -> None:
    """Application factory must bind extensions to the Flask app instance."""
    app = create_app("testing")
    assert "sqlalchemy" in app.extensions
    assert "migrate" in app.extensions
    with app.app_context():
        assert db.engine is not None
    assert migrate.db is db


def test_request_id_middleware(client: Flask) -> None:
    """Application should generate or preserve X-Request-ID on HTTP responses."""
    # When no X-Request-ID is sent, application must generate one
    response = client.get("/health")
    assert "X-Request-ID" in response.headers
    generated_id = response.headers["X-Request-ID"]
    assert len(generated_id) > 0

    # When X-Request-ID is provided by client, application should preserve it
    custom_id = "test-custom-request-id-456"
    response_with_header = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response_with_header.headers.get("X-Request-ID") == custom_id
