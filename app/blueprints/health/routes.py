"""Health check endpoint routes for MediLab AI.

Provides machine-readable service status, distinguishing process health
from database connectivity, without exposing internal secrets or traces.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, make_response
from sqlalchemy import text

from app.extensions import db

health_bp = Blueprint("health", __name__)


def check_database_connectivity() -> tuple[bool, str]:
    """Execute a lightweight probe query against the configured database.

    Returns:
        Tuple of (is_connected, status_description)
    """
    try:
        db.session.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as exc:
        current_app.logger.warning("Database health check probe failed: %s", exc)
        return False, "disconnected"


@health_bp.route("/health", methods=["GET"])
def health_check() -> Any:
    """Return health status of the application and downstream dependencies.

    Returns:
        JSON response with HTTP 200 (healthy) or HTTP 503 (degraded/disconnected).
    """
    db_ok, db_status = check_database_connectivity()

    status = "ok" if db_ok else "degraded"
    status_code = 200 if db_ok else 503

    payload = {
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
        "database": db_status,
    }

    response = make_response(jsonify(payload), status_code)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
