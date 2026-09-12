"""Unit tests for application configuration."""

from __future__ import annotations

import pytest

from app.config import (
    ConfigurationError,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)


def test_development_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    mapping = DevelopmentConfig.as_mapping()

    assert mapping["DEBUG"] is True
    assert mapping["TESTING"] is False
    assert mapping["APP_ENV"] == "development"
    assert mapping["SECRET_KEY"]
    assert mapping["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://")


def test_testing_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    mapping = TestingConfig.as_mapping()

    assert mapping["DEBUG"] is False
    assert mapping["TESTING"] is True
    assert mapping["APP_ENV"] == "testing"
    assert mapping["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_get_config_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDILAB_ENV", "testing")
    assert get_config() is TestingConfig
    assert get_config("development") is DevelopmentConfig


def test_get_config_unknown_name_raises_error() -> None:
    with pytest.raises(ConfigurationError, match="Unknown configuration 'invalid_env'"):
        get_config("invalid_env")


def _valid_production_mapping() -> dict[str, object]:
    mapping = ProductionConfig.as_mapping()
    mapping.update(
        {
            "SECRET_KEY": "a-secure-production-secret-key-with-more-than-32-characters",
            "SQLALCHEMY_DATABASE_URI": (
                "postgresql+psycopg://user:password@db.example.com:5432/medilab"
            ),
            "LOG_LEVEL": "INFO",
        }
    )
    return mapping


def test_production_rejects_insecure_secret() -> None:
    mapping = _valid_production_mapping()
    mapping["SECRET_KEY"] = "too-short"

    with pytest.raises(ConfigurationError, match="minimum 32 characters"):
        ProductionConfig.validate(mapping)


def test_production_rejects_missing_database_url() -> None:
    mapping = _valid_production_mapping()
    mapping["SQLALCHEMY_DATABASE_URI"] = ""

    with pytest.raises(ConfigurationError, match="requires a valid DATABASE_URL"):
        ProductionConfig.validate(mapping)


def test_production_rejects_malformed_database_url() -> None:
    mapping = _valid_production_mapping()
    mapping["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg://[malformed"

    with pytest.raises(ConfigurationError, match="DATABASE_URL is malformed"):
        ProductionConfig.validate(mapping)


def test_production_rejects_non_postgres_database_url() -> None:
    mapping = _valid_production_mapping()
    mapping["SQLALCHEMY_DATABASE_URI"] = "sqlite:///production.db"

    with pytest.raises(ConfigurationError, match="must use PostgreSQL"):
        ProductionConfig.validate(mapping)


def test_production_accepts_valid_parameters() -> None:
    ProductionConfig.validate(_valid_production_mapping())
