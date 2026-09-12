"""Request correlation helpers for MediLab AI HTTP traffic."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from flask import g, request

if TYPE_CHECKING:
    from flask import Flask, Response

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _resolve_request_id(raw_request_id: str | None) -> str:
    """Return a bounded safe request ID or generate a new correlation ID."""
    candidate = (raw_request_id or "").strip()
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def register_request_id_hooks(app: Flask) -> None:
    """Register request/response hooks for correlation IDs."""

    @app.before_request
    def attach_request_id() -> None:
        g.request_id = _resolve_request_id(request.headers.get("X-Request-ID"))

    @app.after_request
    def expose_request_id(response: Response) -> Response:
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response
