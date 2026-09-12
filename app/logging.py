"""Structured logging module for MediLab AI.

Configures consistent, structured log output across the application,
including timestamp, log level, module name, request ID, and message.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from flask import g, has_request_context

if TYPE_CHECKING:
    from flask import Flask


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON entries."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include request ID if inside an active Flask request context
        if has_request_context():
            request_id = getattr(g, "request_id", None)
            if request_id:
                log_data["request_id"] = request_id

        # Include exception information server-side if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include any extra metadata passed via logger call
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_data.update(record.extra_data)

        return json.dumps(log_data)


def setup_logging(app: Flask) -> None:
    """Configure structured logging for the Flask application.

    Args:
        app: Flask application instance.
    """
    log_level_name = app.config.get("LOG_LEVEL", "INFO")
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Avoid adding duplicate handlers if already configured
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    handler.setLevel(log_level)

    # Configure application logger
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False
