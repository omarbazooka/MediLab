"""Unit tests for application configuration."""

import pytest

from app.config import (
    BaseConfig,
    ConfigurationError,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)


def test_development_config_defaults() -> None:
    """DevelopmentConfig should provide sensible defaults for local development."""
    config = DevelopmentConfig
    assert config.DEBUG is True
    assert config.TESTING is False
    assert config.ENV == "development"
    assert config.SECRET_KEY != ""
    assert "postgresql" in config.SQLALCHEMY_DATABASE_URI


def test_testing_config_defaults() -> None:
    """TestingConfig should enable TESTING and default to an in-memory database."""
    config = TestingConfig
    assert config.DEBUG is False
    assert config.TESTING is True
    assert config.ENV == "testing"
    assert config.SQLALCHEMY_DATABASE_URI.startswith("sqlite")


def test_get_config_resolution() -> None:
    """get_config should correctly resolve valid config names."""
    assert get_config("development") == DevelopmentConfig
    assert get_config("testing") == TestingConfig


def test_get_config_unknown_name_raises_error() -> None:
    """get_config should raise ConfigurationError when passed an invalid environment name."""
    with pytest.raises(ConfigurationError, match="Unknown configuration 'invalid_env'"):
        get_config("invalid_env")


def test_invalid_log_level_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """BaseConfig.validate should reject invalid LOG_LEVEL values."""
    monkeypatch.setattr(BaseConfig, "LOG_LEVEL", "NONEXISTENT_LEVEL")
    with pytest.raises(ConfigurationError, match="Invalid LOG_LEVEL"):
        BaseConfig.validate()


def test_production_config_rejects_empty_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProductionConfig must reject empty or whitespace SECRET_KEY."""
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "")
    monkeypatch.setattr(
        ProductionConfig,
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg://user:pass@db:5432/medilab",
    )
    with pytest.raises(
        ConfigurationError, match="Production requires a strong, non-default SECRET_KEY"
    ):
        ProductionConfig.validate()


def test_production_config_rejects_insecure_default_secret_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProductionConfig must reject known insecure default keys."""
    monkeypatch.setattr(
        ProductionConfig,
        "SECRET_KEY",
        "dev-insecure-secret-key-for-local-development-only-12345",
    )
    monkeypatch.setattr(
        ProductionConfig,
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg://user:pass@db:5432/medilab",
    )
    with pytest.raises(
        ConfigurationError, match="Production requires a strong, non-default SECRET_KEY"
    ):
        ProductionConfig.validate()


def test_production_config_rejects_short_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProductionConfig must reject SECRET_KEY that is shorter than 16 characters."""
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "too-short")
    monkeypatch.setattr(
        ProductionConfig,
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg://user:pass@db:5432/medilab",
    )
    with pytest.raises(
        ConfigurationError, match="Production requires a strong, non-default SECRET_KEY"
    ):
        ProductionConfig.validate()


def test_production_config_rejects_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProductionConfig must reject missing DATABASE_URL."""
    monkeypatch.setattr(
        ProductionConfig, "SECRET_KEY", "a-very-secure-random-secret-key-for-production"
    )
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "")
    with pytest.raises(ConfigurationError, match="Production requires a valid DATABASE_URL"):
        ProductionConfig.validate()


def test_production_config_rejects_non_postgres_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProductionConfig must reject non-PostgreSQL database schemes."""
    monkeypatch.setattr(
        ProductionConfig, "SECRET_KEY", "a-very-secure-random-secret-key-for-production"
    )
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "sqlite:///prod.db")
    with pytest.raises(
        ConfigurationError, match="Production DATABASE_URL must use a valid PostgreSQL URI"
    ):
        ProductionConfig.validate()


def test_production_config_accepts_valid_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProductionConfig should pass validation when secure secrets and PostgreSQL are configured."""
    monkeypatch.setattr(
        ProductionConfig, "SECRET_KEY", "a-sufficiently-long-and-secure-random-production-key-987"
    )
    monkeypatch.setattr(
        ProductionConfig,
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg://prod_user:strong_password@db.example.com:5432/medilab_prod",
    )
    # Should execute without raising
    ProductionConfig.validate()
