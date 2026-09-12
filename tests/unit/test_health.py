"""Unit-level HTTP contract tests for the health endpoint."""

from unittest.mock import patch

from flask.testing import FlaskClient


def test_health_check_healthy_with_test_database(client: FlaskClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "timestamp" in data
    assert response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"


def test_health_check_database_failure_is_controlled(client: FlaskClient) -> None:
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
