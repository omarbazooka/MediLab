"""MediLab AI Flask application package."""

from __future__ import annotations

from typing import Any

from flask import Flask

import app.models  # noqa: F401
from app.blueprints import register_blueprints
from app.config import get_config, load_environment_file
from app.errors import register_error_handlers
from app.extensions import db, migrate
from app.logging import setup_logging
from app.request_ids import register_request_id_hooks


def create_app(
    config_name: str | None = None,
    test_config: dict[str, Any] | None = None,
) -> Flask:
    """Create and configure a MediLab AI Flask application instance."""
    load_environment_file()

    app = Flask(__name__)
    config_class = get_config(config_name)
    app.config.from_mapping(config_class.as_mapping())

    if test_config:
        app.config.update(test_config)

    config_class.validate(app.config)

    setup_logging(app)
    db.init_app(app)
    migrate.init_app(app, db)

    register_request_id_hooks(app)
    register_error_handlers(app)
    register_blueprints(app)

    return app
