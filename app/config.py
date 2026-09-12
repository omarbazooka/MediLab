"""Configuration module for MediLab AI application.

Provides distinct environment configurations:
- DevelopmentConfig: Local developer settings with sensible defaults
- TestingConfig: Isolated testing settings with fast in-memory database
- ProductionConfig: Strict production settings with validation of required secrets
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid or missing required values."""


class BaseConfig:
    """Base configuration shared across all environments."""

    ENV: str = "production"
    DEBUG: bool = False
    TESTING: bool = False

    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI: str = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {
        "pool_pre_ping": True,
    }

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def validate(cls) -> None:
        """Validate configuration settings. Override in subclasses for strict checks."""
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if cls.LOG_LEVEL not in valid_log_levels:
            valid_str = ", ".join(sorted(valid_log_levels))
            raise ConfigurationError(
                f"Invalid LOG_LEVEL '{cls.LOG_LEVEL}'. Must be one of: {valid_str}"
            )


class DevelopmentConfig(BaseConfig):
    """Configuration for local development."""

    ENV: str = "development"
    DEBUG: bool = True
    TESTING: bool = False

    # Safe convenience defaults for local development
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "dev-insecure-secret-key-for-local-development-only-12345"
    )
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/medilab"
    )


class TestingConfig(BaseConfig):
    """Configuration for automated test execution."""

    ENV: str = "testing"
    DEBUG: bool = False
    TESTING: bool = True

    SECRET_KEY: str = "test-secret-key-isolated-for-pytest-execution-only"
    # Default to in-memory SQLite for fast, decoupled unit testing
    # unless TEST_DATABASE_URL is provided
    SQLALCHEMY_DATABASE_URI: str = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    LOG_LEVEL: str = "WARNING"


class ProductionConfig(BaseConfig):
    """Configuration for production deployment with strict validation."""

    ENV: str = "production"
    DEBUG: bool = False
    TESTING: bool = False

    _INSECURE_SECRET_KEYS: set[str] = {
        "",
        "dev-insecure-secret-key-for-local-development-only-12345",
        "change-me-in-production-use-a-secure-random-key",
        "test-secret-key-isolated-for-pytest-execution-only",
        "secret",
        "changeme",
    }

    @classmethod
    def validate(cls) -> None:
        """Enforce strict production configuration requirements."""
        super().validate()

        secret_key = cls.SECRET_KEY.strip()
        if not secret_key or secret_key in cls._INSECURE_SECRET_KEYS or len(secret_key) < 16:
            raise ConfigurationError(
                "Production requires a strong, non-default SECRET_KEY environment variable "
                "(minimum 16 characters)."
            )

        db_uri = cls.SQLALCHEMY_DATABASE_URI.strip()
        if not db_uri:
            raise ConfigurationError(
                "Production requires a valid DATABASE_URL environment variable."
            )
        if not (db_uri.startswith("postgresql://") or db_uri.startswith("postgresql+psycopg://")):
            raise ConfigurationError(
                "Production DATABASE_URL must use a valid PostgreSQL URI (e.g. postgresql+psycopg://...)."
            )


CONFIG_MAP: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name: str | None = None) -> type[BaseConfig]:
    """Resolve and return configuration class based on parameter or FLASK_ENV.

    Args:
        config_name: Optional explicit environment name ('development', 'testing', 'production')

    Returns:
        The matching configuration class.

    Raises:
        ConfigurationError: If an unknown configuration name is specified.
    """
    env_name = (config_name or os.getenv("FLASK_ENV", "development")).lower().strip()
    config_class = CONFIG_MAP.get(env_name)
    if not config_class:
        available = ", ".join(CONFIG_MAP.keys())
        raise ConfigurationError(
            f"Unknown configuration '{env_name}'. Available environments: {available}"
        )

    # Perform validation
    config_class.validate()
    return config_class
