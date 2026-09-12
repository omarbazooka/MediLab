"""Structured logging for MediLab AI."""

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
    """Format application log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if has_request_context():
            request_id = getattr(g, "request_id", None)
            if request_id:
                log_data["request_id"] = request_id

        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict) and extra_data:
            log_data["context"] = extra_data

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(app: Flask) -> None:
    """Configure a single structured stdout handler for the Flask app logger."""
    log_level_name = str(app.config.get("LOG_LEVEL", "INFO")).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    handler.setLevel(log_level)

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False
