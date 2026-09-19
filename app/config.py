"""Application configuration for MediLab AI.

Configuration values are resolved when the application factory runs, not at
module import time. This keeps tests deterministic and avoids hidden side
effects while preserving strict production validation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid or incomplete."""


class BaseConfig:
    """Base settings shared across all application environments."""

    APP_ENV = "production"
    DEBUG = False
    TESTING = False
    DEFAULT_SECRET_KEY = ""
    DEFAULT_DATABASE_URL = ""
    DEFAULT_LOG_LEVEL = "INFO"
    DEFAULT_EMBEDDING_PROVIDER = "jina"
    DEFAULT_EMBEDDING_MODEL = "jina-embeddings-v3"
    DEFAULT_EMBEDDING_DIMENSION = 384
    DEFAULT_LLM_PROVIDER = "fake"
    DEFAULT_LLM_MODEL = "gpt-4o-mini"
    DEFAULT_LLM_BASE_URL = ""

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {"pool_pre_ping": True}

    @classmethod
    def as_mapping(cls) -> dict[str, Any]:
        """Resolve environment-backed values for a fresh Flask app instance."""
        try:
            dim_raw = os.getenv("EMBEDDING_DIMENSION", str(cls.DEFAULT_EMBEDDING_DIMENSION))
            dimension = int(dim_raw)
        except (TypeError, ValueError):
            dimension = -1

        return {
            "APP_ENV": cls.APP_ENV,
            "DEBUG": cls.DEBUG,
            "TESTING": cls.TESTING,
            "SECRET_KEY": os.getenv("SECRET_KEY", cls.DEFAULT_SECRET_KEY),
            "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL", cls.DEFAULT_DATABASE_URL),
            "SQLALCHEMY_TRACK_MODIFICATIONS": cls.SQLALCHEMY_TRACK_MODIFICATIONS,
            "SQLALCHEMY_ENGINE_OPTIONS": cls.SQLALCHEMY_ENGINE_OPTIONS.copy(),
            "LOG_LEVEL": os.getenv("LOG_LEVEL", cls.DEFAULT_LOG_LEVEL).upper(),
            "EMBEDDING_PROVIDER": os.getenv("EMBEDDING_PROVIDER", cls.DEFAULT_EMBEDDING_PROVIDER)
            .strip()
            .lower(),
            "EMBEDDING_MODEL": os.getenv("EMBEDDING_MODEL", cls.DEFAULT_EMBEDDING_MODEL).strip(),
            "EMBEDDING_DIMENSION": dimension,
            "JINA_API_KEY": os.getenv("JINA_API_KEY", "").strip(),
            "LLM_PROVIDER": os.getenv("LLM_PROVIDER", cls.DEFAULT_LLM_PROVIDER).strip().lower(),
            "LLM_MODEL": os.getenv("LLM_MODEL", cls.DEFAULT_LLM_MODEL).strip(),
            "LLM_API_KEY": (
                os.getenv("LLM_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or ""
            ).strip(),
            "LLM_BASE_URL": os.getenv("LLM_BASE_URL", cls.DEFAULT_LLM_BASE_URL).strip(),
        }

    @classmethod
    def validate(cls, config: Mapping[str, Any]) -> None:
        """Validate settings common to every environment."""
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        log_level = str(config.get("LOG_LEVEL", "")).upper()
        if log_level not in valid_log_levels:
            valid_str = ", ".join(sorted(valid_log_levels))
            raise ConfigurationError(
                f"Invalid LOG_LEVEL '{log_level}'. Must be one of: {valid_str}"
            )

        # Validate embedding settings
        provider = str(config.get("EMBEDDING_PROVIDER", "")).strip().lower()
        if provider not in {"jina"}:
            raise ConfigurationError(
                f"Unsupported EMBEDDING_PROVIDER '{provider}'. Supported providers: jina"
            )

        # Validate LLM provider settings
        llm_provider = str(config.get("LLM_PROVIDER", "")).strip().lower()
        valid_llm_providers = {"fake", "openai", "gemini", "groq", "openrouter"}
        if llm_provider not in valid_llm_providers:
            valid_str = ", ".join(sorted(valid_llm_providers))
            raise ConfigurationError(
                f"Unsupported LLM_PROVIDER '{llm_provider}'. Supported providers: {valid_str}"
            )

        dimension = config.get("EMBEDDING_DIMENSION")
        if not isinstance(dimension, int) or dimension <= 0:
            raise ConfigurationError(
                f"Invalid EMBEDDING_DIMENSION '{dimension}'. Dimension must be a positive integer."
            )
        if provider == "jina" and dimension != 384:
            raise ConfigurationError(
                f"MediLab Jina embedding configuration expects dimension 384, got {dimension}."
            )


class DevelopmentConfig(BaseConfig):
    """Local development settings with explicitly insecure convenience defaults."""

    APP_ENV = "development"
    DEBUG = True
    DEFAULT_SECRET_KEY = "dev-insecure-secret-key-for-local-development-only-12345"
    DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab"


class TestingConfig(BaseConfig):
    """Fast isolated defaults for unit tests."""

    APP_ENV = "testing"
    TESTING = True
    DEFAULT_SECRET_KEY = "test-secret-key-isolated-for-pytest-execution-only"
    DEFAULT_DATABASE_URL = "sqlite:///:memory:"
    DEFAULT_LOG_LEVEL = "WARNING"

    @classmethod
    def as_mapping(cls) -> dict[str, Any]:
        mapping = super().as_mapping()
        mapping["SQLALCHEMY_DATABASE_URI"] = os.getenv(
            "TEST_DATABASE_URL", cls.DEFAULT_DATABASE_URL
        )
        return mapping


class ProductionConfig(BaseConfig):
    """Production settings with strict secret and PostgreSQL validation."""

    APP_ENV = "production"

    _INSECURE_SECRET_KEYS = {
        "",
        DevelopmentConfig.DEFAULT_SECRET_KEY,
        TestingConfig.DEFAULT_SECRET_KEY,
        "change-me-in-production-use-a-secure-random-key",
        "secret",
        "changeme",
    }

    @classmethod
    def validate(cls, config: Mapping[str, Any]) -> None:
        super().validate(config)

        secret_key = str(config.get("SECRET_KEY", "")).strip()
        if secret_key in cls._INSECURE_SECRET_KEYS or len(secret_key) < 32:
            raise ConfigurationError(
                "Production requires a strong, non-default SECRET_KEY (minimum 32 characters)."
            )

        database_url = str(config.get("SQLALCHEMY_DATABASE_URI", "")).strip()
        if not database_url:
            raise ConfigurationError(
                "Production requires a valid DATABASE_URL environment variable."
            )

        try:
            # urllib validates authority syntax (including malformed IPv6 brackets),
            # while SQLAlchemy validates/normalizes the database URL dialect.
            split_url = urlsplit(database_url)
            _ = split_url.hostname
            parsed_url = make_url(database_url)
        except (ArgumentError, ValueError) as exc:
            raise ConfigurationError("Production DATABASE_URL is malformed.") from exc

        if parsed_url.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise ConfigurationError("Production DATABASE_URL must use PostgreSQL with psycopg.")
        if not parsed_url.database:
            raise ConfigurationError("Production DATABASE_URL must include a database name.")


CONFIG_MAP: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def load_environment_file() -> None:
    """Load local `.env` values when present without overriding real env vars."""
    load_dotenv(BASE_DIR / ".env", override=False)


def get_config(config_name: str | None = None) -> type[BaseConfig]:
    """Resolve a configuration class from an explicit name or MEDILAB_ENV."""
    environment = (config_name or os.getenv("MEDILAB_ENV", "development")).strip().lower()
    config_class = CONFIG_MAP.get(environment)
    if config_class is None:
        available = ", ".join(CONFIG_MAP)
        raise ConfigurationError(
            f"Unknown configuration '{environment}'. Available environments: {available}"
        )
    return config_class
