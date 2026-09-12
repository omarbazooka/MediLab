"""Blueprint registration for MediLab AI.

Keep HTTP surfaces grouped by responsibility. Future customer, chat API, and
admin blueprints can be registered here without growing the application factory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.blueprints.health import health_bp

if TYPE_CHECKING:
    from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all Phase 0 HTTP blueprints."""
    app.register_blueprint(health_bp)
