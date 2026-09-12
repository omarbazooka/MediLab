"""Unit tests for centralized error handling."""

from flask import Flask
from flask.testing import FlaskClient


def test_404_not_found_returns_json(client: FlaskClient) -> None:
    """Requesting an unknown route should return structured 404 JSON."""
    response = client.get("/nonexistent-endpoint-xyz")
    assert response.status_code == 404
    assert response.is_json

    data = response.get_json()
    assert "error" in data
    assert data["error"]["code"] == "not_found"
    assert "not found" in data["error"]["message"].lower()


def test_405_method_not_allowed(client: FlaskClient) -> None:
    """Calling an endpoint with an unsupported HTTP method should return structured 405 JSON."""
    response = client.post("/health")
    assert response.status_code == 405
    assert response.is_json

    data = response.get_json()
    assert "error" in data
    assert data["error"]["code"] == "method_not_allowed"


def test_500_internal_server_error_suppresses_traceback(app: Flask) -> None:
    """Unhandled internal exceptions must return safe 500 JSON without leaking tracebacks."""

    # Register a temporary test route that intentionally raises an exception
    @app.route("/test-error-500")
    def trigger_error() -> None:
        raise RuntimeError("Sensitive internal database connection detail or secret password")

    # Disable testing exception propagation so the error handler catches the exception
    app.config["TESTING"] = False
    test_client = app.test_client()

    response = test_client.get("/test-error-500")
    assert response.status_code == 500
    assert response.is_json

    data = response.get_json()
    assert "error" in data
    assert data["error"]["code"] == "internal_server_error"
    # Verify sensitive error details/tracebacks are not leaked in the client response
    assert "Sensitive internal database connection detail" not in data["error"]["message"]
    assert "Traceback" not in response.get_data(as_text=True)
