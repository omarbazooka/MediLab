"""Customer-facing Flask/Jinja experience."""

from flask import Blueprint

customer_bp = Blueprint("customer", __name__)

from app.blueprints.customer import routes  # noqa: E402, F401
