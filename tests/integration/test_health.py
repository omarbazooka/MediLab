"""Health endpoint integration test against real PostgreSQL."""

import pytest
from flask.testing import FlaskClient

pytestmark = pytest.mark.postgres


def test_health_check_with_postgresql(postgres_client: FlaskClient) -> None:
    response = postgres_client.get("/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
