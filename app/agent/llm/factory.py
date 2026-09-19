"""LLM Provider Factory for MediLab AI.

Ensures Google Gemini is the sole production LLM provider, with FakeLLMProvider
strictly constrained to explicit testing configurations. Never silently falls back
from Gemini to Fake when credentials are missing.
"""

from __future__ import annotations

import os
from typing import Any

from flask import current_app

from app.agent.llm.base import LLMProvider
from app.agent.llm.fake import FakeLLMProvider
from app.agent.llm.gemini_provider import GeminiProvider
from app.config import ConfigurationError

_OVERRIDE_PROVIDER: LLMProvider | None = None


def set_override_llm_provider(provider: LLMProvider | None) -> None:
    """Set or clear a process-level LLM provider override (used in unit/integration tests)."""
    global _OVERRIDE_PROVIDER
    _OVERRIDE_PROVIDER = provider


def get_llm_provider(
    provider_name: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    """Resolve and instantiate the configured LLM provider.

    Raises ConfigurationError if Gemini is selected without credentials,
    or if Fake is requested outside of testing environments.
    """
    global _OVERRIDE_PROVIDER
    if _OVERRIDE_PROVIDER is not None:
        return _OVERRIDE_PROVIDER

    # Check Flask config if available, fallback to os.environ
    config: dict[str, Any] = {}
    try:
        if current_app:
            config = dict(current_app.config)
    except RuntimeError:
        pass

    resolved_provider = (
        (provider_name or config.get("LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "gemini"))
        .strip()
        .lower()
    )

    is_testing = bool(
        config.get("TESTING", False)
        or os.getenv("MEDILAB_ENV") == "testing"
        or os.getenv("TESTING") == "true"
    )

    if resolved_provider == "fake":
        if not is_testing:
            raise ConfigurationError(
                "LLM_PROVIDER 'fake' is only permitted in testing environments or via explicit test overrides."
            )
        return FakeLLMProvider()

    if resolved_provider == "gemini":
        resolved_api_key = (
            api_key or config.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
        ).strip()
        if not resolved_api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY is required when LLM_PROVIDER is 'gemini'. "
                "MediLab will not silently fall back to Fake provider in real runtime."
            )

        resolved_model = (
            model or config.get("LLM_MODEL") or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        ).strip()
        timeout = float(config.get("LLM_TIMEOUT_SECONDS") or os.getenv("LLM_TIMEOUT_SECONDS", 30.0))
        temperature = float(config.get("LLM_TEMPERATURE") or os.getenv("LLM_TEMPERATURE", 0.0))
        max_retries = int(config.get("LLM_MAX_RETRIES") or os.getenv("LLM_MAX_RETRIES", 1))

        return GeminiProvider(
            api_key=resolved_api_key,
            model=resolved_model,
            timeout_seconds=timeout,
            temperature=temperature,
            max_retries=max_retries,
        )

    raise ConfigurationError(
        f"Unsupported LLM_PROVIDER '{resolved_provider}'. MediLab runtime supports 'gemini' (or 'fake' in tests)."
    )
