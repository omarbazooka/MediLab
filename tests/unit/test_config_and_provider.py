"""Unit tests for Gemini-only configuration validation, factory behavior, and error sanitization."""

from __future__ import annotations

import pytest

from app.agent.llm.factory import get_llm_provider
from app.agent.llm.gemini_provider import GeminiProvider
from app.agent.schemas import SafetyCategory
from app.config import BaseConfig, ConfigurationError, TestingConfig


def test_gemini_config_missing_api_key_raises_error() -> None:
    """When LLM_PROVIDER is gemini and not in testing, missing GEMINI_API_KEY must fail explicitly."""
    cfg = {
        "LOG_LEVEL": "INFO",
        "EMBEDDING_PROVIDER": "jina",
        "EMBEDDING_DIMENSION": 384,
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "",
        "LLM_MODEL": "gemini-2.5-flash",
        "TESTING": False,
        "LLM_TIMEOUT_SECONDS": 30.0,
        "LLM_MAX_RETRIES": 1,
        "LLM_TEMPERATURE": 0.0,
        "MAX_RECENT_MESSAGES": 10,
        "MAX_CUSTOMER_BOOKINGS": 5,
        "MAX_CLARIFICATION_ATTEMPTS": 2,
        "MAX_INPUT_LENGTH": 1000,
    }
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is required"):
        BaseConfig.validate(cfg)


def test_fake_provider_forbidden_outside_testing() -> None:
    """LLM_PROVIDER 'fake' is strictly rejected when TESTING is False."""
    cfg = {
        "LOG_LEVEL": "INFO",
        "EMBEDDING_PROVIDER": "jina",
        "EMBEDDING_DIMENSION": 384,
        "LLM_PROVIDER": "fake",
        "TESTING": False,
        "LLM_TIMEOUT_SECONDS": 30.0,
        "LLM_MAX_RETRIES": 1,
        "LLM_TEMPERATURE": 0.0,
        "MAX_RECENT_MESSAGES": 10,
        "MAX_CUSTOMER_BOOKINGS": 5,
        "MAX_CLARIFICATION_ATTEMPTS": 2,
        "MAX_INPUT_LENGTH": 1000,
    }
    with pytest.raises(ConfigurationError, match="only permitted when TESTING is True"):
        BaseConfig.validate(cfg)


def test_unsupported_provider_raises_error() -> None:
    """Providers other than gemini/fake (e.g. openai, groq) are rejected."""
    cfg = {
        "LOG_LEVEL": "INFO",
        "EMBEDDING_PROVIDER": "jina",
        "EMBEDDING_DIMENSION": 384,
        "LLM_PROVIDER": "openai",
        "TESTING": False,
        "LLM_TIMEOUT_SECONDS": 30.0,
        "LLM_MAX_RETRIES": 1,
        "LLM_TEMPERATURE": 0.0,
        "MAX_RECENT_MESSAGES": 10,
        "MAX_CUSTOMER_BOOKINGS": 5,
        "MAX_CLARIFICATION_ATTEMPTS": 2,
        "MAX_INPUT_LENGTH": 1000,
    }
    with pytest.raises(ConfigurationError, match="Unsupported LLM_PROVIDER"):
        BaseConfig.validate(cfg)


def test_numeric_limits_validation() -> None:
    """Ensure invalid timeouts, temperatures, or limits raise ConfigurationError."""
    base = {
        "LOG_LEVEL": "INFO",
        "EMBEDDING_PROVIDER": "jina",
        "EMBEDDING_DIMENSION": 384,
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "dummy-key",
        "LLM_MODEL": "gemini-2.5-flash",
        "TESTING": True,
        "LLM_TIMEOUT_SECONDS": 30.0,
        "LLM_MAX_RETRIES": 1,
        "LLM_TEMPERATURE": 0.0,
        "MAX_RECENT_MESSAGES": 10,
        "MAX_CUSTOMER_BOOKINGS": 5,
        "MAX_CLARIFICATION_ATTEMPTS": 2,
        "MAX_INPUT_LENGTH": 1000,
    }

    with pytest.raises(ConfigurationError, match="LLM_TIMEOUT_SECONDS"):
        BaseConfig.validate({**base, "LLM_TIMEOUT_SECONDS": -5})

    with pytest.raises(ConfigurationError, match="LLM_TEMPERATURE"):
        BaseConfig.validate({**base, "LLM_TEMPERATURE": 3.5})

    with pytest.raises(ConfigurationError, match="MAX_RECENT_MESSAGES"):
        BaseConfig.validate({**base, "MAX_RECENT_MESSAGES": 0})


def test_testing_config_forces_fake_even_with_ambient_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer .env containing Gemini config must never make ordinary tests call Google."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "ambient-real-like-secret")

    mapping = TestingConfig.as_mapping()

    assert mapping["TESTING"] is True
    assert mapping["LLM_PROVIDER"] == "fake"
    assert mapping["GEMINI_API_KEY"] == ""


def test_no_silent_fallback_in_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Factory must raise ConfigurationError when Gemini credentials are missing, never return Fake."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is required"):
        get_llm_provider(provider_name="gemini", api_key="")


def test_gemini_error_sanitization() -> None:
    """Sensitive API keys and URL params must be redacted from error messages."""
    fake_secret = "AIzaSySecretApiKey123456789"
    provider = GeminiProvider(api_key=fake_secret)

    sample_error = (
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        f"?key={fake_secret} failed with 403 Forbidden"
    )

    sanitized = provider._sanitize_error_text(sample_error)
    assert fake_secret not in sanitized
    assert "[REDACTED" in sanitized


def test_gemini_safety_fails_closed_on_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider errors are simulated locally; unit tests must never depend on Google's network."""
    provider = GeminiProvider(api_key="unit-test-secret")

    def raise_provider_error(*args: object, **kwargs: object) -> str:
        raise RuntimeError("Gemini API call failed for ?key=unit-test-secret with synthetic 503")

    monkeypatch.setattr(provider, "_call_generate_content", raise_provider_error)
    classification = provider.classify_safety("What is CBC?")

    assert classification.is_safe is False
    assert classification.category == SafetyCategory.OTHER_CLINICAL_UNSAFE
    assert classification.reason == "Safety classification unavailable; failing closed."
    assert "unit-test-secret" not in (classification.reason or "")
