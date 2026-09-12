"""MediLab AI Application Package.

Implements the Flask application factory pattern.
"""

from __future__ import annotations

import uuid
from typing import Any

from flask import Flask, Response, g, request

from app.blueprints.health import health_bp
from app.config import get_config
from app.errors import register_error_handlers
from app.extensions import db, migrate
from app.logging import setup_logging


def create_app(
    config_name: str | None = None,
    test_config: dict[str, Any] | None = None,
) -> Flask:
    """Create and configure an instance of the MediLab AI Flask application.

    Args:
        config_name: Optional environment name ('development', 'testing', 'production').
        test_config: Optional configuration dictionary override for testing.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    # Load configuration
    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Apply testing configuration overrides if provided
    if test_config:
        app.config.update(test_config)

    # Setup structured logging
    setup_logging(app)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register request lifecycle hooks (Request ID propagation)
    @app.before_request
    def before_request_hook() -> None:
        incoming_request_id = request.headers.get("X-Request-ID")
        g.request_id = incoming_request_id or uuid.uuid4().hex

    @app.after_request
    def after_request_hook(response: Response) -> Response:
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response

    # Register centralized error handlers
    register_error_handlers(app)

    # Register blueprints
    app.register_blueprint(health_bp)

    return app
