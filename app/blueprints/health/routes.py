"""Operational health endpoints for MediLab AI."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, make_response
from sqlalchemy import text

from app.extensions import db

health_bp = Blueprint("health", __name__)


def check_database_connectivity() -> tuple[bool, str]:
    """Probe the configured database without mutating request-scoped ORM state."""
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as exc:  # health boundary: all DB/driver failures degrade safely
        current_app.logger.warning(
            "Database health check failed",
            extra={"extra_data": {"error_type": type(exc).__name__}},
        )
        return False, "disconnected"


@health_bp.get("/health")
def health_check() -> Any:
    """Return process and database readiness as machine-readable JSON."""
    db_ok, db_status = check_database_connectivity()
    status_code = 200 if db_ok else 503

    response = make_response(
        jsonify(
            {
                "status": "ok" if db_ok else "degraded",
                "timestamp": datetime.now(UTC).isoformat(),
                "database": db_status,
            }
        ),
        status_code,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
