"""Integration tests for the /health check endpoint."""

from unittest.mock import patch

from flask.testing import FlaskClient


def test_health_check_healthy(client: FlaskClient) -> None:
    """GET /health should return 200 OK and healthy status when database is reachable."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "timestamp" in data
    assert response.headers.get("Cache-Control") == "no-cache, no-store, must-revalidate"


def test_health_check_database_failure(client: FlaskClient) -> None:
    """GET /health should return 503 and degraded status when database is unreachable."""
    with patch(
        "app.blueprints.health.routes.check_database_connectivity",
        return_value=(False, "disconnected"),
    ):
        response = client.get("/health")
        assert response.status_code == 503
        assert response.is_json

        data = response.get_json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
        assert "timestamp" in data
