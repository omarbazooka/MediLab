"""LLM Provider Factory for MediLab AI."""

from __future__ import annotations

import os
from typing import Any

from flask import current_app

from app.agent.llm.base import LLMProvider
from app.agent.llm.fake import FakeLLMProvider
from app.agent.llm.gemini_provider import GeminiProvider
from app.agent.llm.openai_provider import OpenAICompatibleProvider

_OVERRIDE_PROVIDER: LLMProvider | None = None


def set_override_llm_provider(provider: LLMProvider | None) -> None:
    """Set or clear a process-level LLM provider override (used in unit/integration tests)."""
    global _OVERRIDE_PROVIDER
    _OVERRIDE_PROVIDER = provider


def get_llm_provider(
    provider_name: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Resolve and instantiate the configured LLM provider."""
    global _OVERRIDE_PROVIDER
    if _OVERRIDE_PROVIDER is not None:
        return _OVERRIDE_PROVIDER

    # Check Flask config if available, fallback to os.environ
    config: dict[str, Any] = {}
    try:
        if current_app:
            config = current_app.config
    except RuntimeError:
        pass

    resolved_provider = (
        (provider_name or config.get("LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "fake"))
        .strip()
        .lower()
    )

    resolved_api_key = (
        api_key
        or config.get("LLM_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or ""
    ).strip()

    resolved_model = (model or config.get("LLM_MODEL") or os.getenv("LLM_MODEL") or "").strip()

    resolved_base_url = (
        base_url or config.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL") or ""
    ).strip()

    if resolved_provider == "fake" or not resolved_api_key:
        return FakeLLMProvider()

    if resolved_provider == "gemini":
        default_gemini_model = resolved_model or "gemini-1.5-flash"
        return GeminiProvider(api_key=resolved_api_key, model=default_gemini_model)

    if resolved_provider in {"openai", "groq", "openrouter"}:
        default_model = resolved_model or (
            "gpt-4o-mini" if resolved_provider == "openai" else "llama-3.1-8b-instant"
        )
        default_base_url = resolved_base_url or (
            "https://api.groq.com/openai/v1"
            if resolved_provider == "groq"
            else "https://api.openai.com/v1"
        )
        return OpenAICompatibleProvider(
            api_key=resolved_api_key,
            model=default_model,
            base_url=default_base_url,
        )

    # Default fallback
    return FakeLLMProvider()
