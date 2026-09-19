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
    DEFAULT_LLM_PROVIDER = "gemini"
    DEFAULT_LLM_MODEL = "gemini-2.5-flash"
    DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
    DEFAULT_LLM_MAX_RETRIES = 1
    DEFAULT_LLM_TEMPERATURE = 0.0

    DEFAULT_MAX_RECENT_MESSAGES = 10
    DEFAULT_MAX_CUSTOMER_BOOKINGS = 5
    DEFAULT_MAX_CLARIFICATION_ATTEMPTS = 2
    DEFAULT_MAX_INPUT_LENGTH = 1000

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

        try:
            timeout_sec = float(
                os.getenv("LLM_TIMEOUT_SECONDS", str(cls.DEFAULT_LLM_TIMEOUT_SECONDS))
            )
        except (TypeError, ValueError):
            timeout_sec = -1.0

        try:
            max_retries = int(os.getenv("LLM_MAX_RETRIES", str(cls.DEFAULT_LLM_MAX_RETRIES)))
        except (TypeError, ValueError):
            max_retries = -1

        try:
            temperature = float(os.getenv("LLM_TEMPERATURE", str(cls.DEFAULT_LLM_TEMPERATURE)))
        except (TypeError, ValueError):
            temperature = -1.0

        try:
            max_recent_msgs = int(
                os.getenv("MAX_RECENT_MESSAGES", str(cls.DEFAULT_MAX_RECENT_MESSAGES))
            )
        except (TypeError, ValueError):
            max_recent_msgs = -1

        try:
            max_cust_bookings = int(
                os.getenv("MAX_CUSTOMER_BOOKINGS", str(cls.DEFAULT_MAX_CUSTOMER_BOOKINGS))
            )
        except (TypeError, ValueError):
            max_cust_bookings = -1

        try:
            max_clarif_attempts = int(
                os.getenv("MAX_CLARIFICATION_ATTEMPTS", str(cls.DEFAULT_MAX_CLARIFICATION_ATTEMPTS))
            )
        except (TypeError, ValueError):
            max_clarif_attempts = -1

        try:
            max_input_len = int(os.getenv("MAX_INPUT_LENGTH", str(cls.DEFAULT_MAX_INPUT_LENGTH)))
        except (TypeError, ValueError):
            max_input_len = -1

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
            "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", "").strip(),
            "LLM_TIMEOUT_SECONDS": timeout_sec,
            "LLM_MAX_RETRIES": max_retries,
            "LLM_TEMPERATURE": temperature,
            "MAX_RECENT_MESSAGES": max_recent_msgs,
            "MAX_CUSTOMER_BOOKINGS": max_cust_bookings,
            "MAX_CLARIFICATION_ATTEMPTS": max_clarif_attempts,
            "MAX_INPUT_LENGTH": max_input_len,
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

        dimension = config.get("EMBEDDING_DIMENSION")
        if not isinstance(dimension, int) or dimension <= 0:
            raise ConfigurationError(
                f"Invalid EMBEDDING_DIMENSION '{dimension}'. Dimension must be a positive integer."
            )
        if provider == "jina" and dimension != 384:
            raise ConfigurationError(
                f"MediLab Jina embedding configuration expects dimension 384, got {dimension}."
            )

        # Validate LLM provider settings (Gemini is the only real provider)
        llm_provider = str(config.get("LLM_PROVIDER", "")).strip().lower()
        if llm_provider not in {"gemini", "fake"}:
            raise ConfigurationError(
                f"Unsupported LLM_PROVIDER '{llm_provider}'. Supported providers: gemini (or fake in testing)"
            )

        is_testing = bool(config.get("TESTING", False))
        if llm_provider == "fake" and not is_testing:
            raise ConfigurationError(
                "LLM_PROVIDER 'fake' is only permitted when TESTING is True or in testing environments."
            )

        if llm_provider == "gemini" and not is_testing:
            gemini_key = str(config.get("GEMINI_API_KEY", "")).strip()
            if not gemini_key:
                raise ConfigurationError(
                    "GEMINI_API_KEY is required and cannot be empty when LLM_PROVIDER is 'gemini'."
                )
            gemini_model = str(config.get("LLM_MODEL", "")).strip()
            if not gemini_model:
                raise ConfigurationError("LLM_MODEL is required when LLM_PROVIDER is 'gemini'.")

        timeout = config.get("LLM_TIMEOUT_SECONDS")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ConfigurationError(
                f"Invalid LLM_TIMEOUT_SECONDS '{timeout}'. Must be a positive number."
            )

        retries = config.get("LLM_MAX_RETRIES")
        if not isinstance(retries, int) or retries < 0:
            raise ConfigurationError(
                f"Invalid LLM_MAX_RETRIES '{retries}'. Must be a non-negative integer."
            )

        temp = config.get("LLM_TEMPERATURE")
        if not isinstance(temp, (int, float)) or not (0.0 <= temp <= 2.0):
            raise ConfigurationError(
                f"Invalid LLM_TEMPERATURE '{temp}'. Must be between 0.0 and 2.0."
            )

        for var_name in (
            "MAX_RECENT_MESSAGES",
            "MAX_CUSTOMER_BOOKINGS",
            "MAX_CLARIFICATION_ATTEMPTS",
            "MAX_INPUT_LENGTH",
        ):
            val = config.get(var_name)
            if not isinstance(val, int) or val <= 0:
                raise ConfigurationError(f"Invalid {var_name} '{val}'. Must be a positive integer.")


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
    DEFAULT_LLM_PROVIDER = "fake"

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
