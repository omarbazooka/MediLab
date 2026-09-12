"""Pytest fixtures for MediLab AI tests."""

from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.extensions import db


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create a Flask application configured for isolated testing."""
    app_instance = create_app(
        config_name="testing",
        test_config={
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
        },
    )

    with app_instance.app_context():
        db.create_all()
        yield app_instance
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Provide a test client for simulating HTTP requests."""
    return app.test_client()
