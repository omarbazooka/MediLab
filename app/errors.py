"""Centralized error handling for MediLab AI application.

Provides consistent JSON responses for HTTP errors and uncaught exceptions.
Prevents internal traces or sensitive details from leaking to clients.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import current_app, jsonify
from werkzeug.exceptions import HTTPException

if TYPE_CHECKING:
    from flask import Flask, Response


def make_error_response(code: str, message: str, status_code: int) -> Response:
    """Generate a consistent JSON error response.

    Args:
        code: Machine-readable error code slug.
        message: Human-readable safe explanation.
        status_code: HTTP status code.

    Returns:
        Flask JSON response with matching HTTP status code.
    """
    payload = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    response = jsonify(payload)
    response.status_code = status_code
    return response


def register_error_handlers(app: Flask) -> None:
    """Register application-wide error handlers on the Flask application instance."""

    @app.errorhandler(400)
    def handle_bad_request(error: HTTPException) -> Response:
        return make_error_response(
            code="bad_request",
            message=error.description or "The request is malformed or invalid.",
            status_code=400,
        )

    @app.errorhandler(404)
    def handle_not_found(error: HTTPException) -> Response:
        return make_error_response(
            code="not_found",
            message="The requested resource was not found.",
            status_code=404,
        )

    @app.errorhandler(405)
    def handle_method_not_allowed(error: HTTPException) -> Response:
        return make_error_response(
            code="method_not_allowed",
            message="The HTTP method is not allowed for the requested resource.",
            status_code=405,
        )

    @app.errorhandler(Exception)
    def handle_internal_server_error(error: Exception) -> Response:
        # If it is a known Werkzeug HTTPException, use its code
        if isinstance(error, HTTPException):
            return make_error_response(
                code=error.name.lower().replace(" ", "_"),
                message=error.description,
                status_code=error.code or 500,
            )

        # Log unhandled exceptions with full stack trace server-side
        current_app.logger.error("Unhandled internal server exception: %s", error, exc_info=True)

        # Return sanitized, generic error payload to the client
        return make_error_response(
            code="internal_server_error",
            message="An unexpected internal server error occurred.",
            status_code=500,
        )
