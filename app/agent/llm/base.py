"""Abstract base class and protocol for MediLab LLM providers."""

from __future__ import annotations

from typing import Any, Protocol

from app.agent.schemas import (
    RequestPlan,
    ResponseDraft,
    SafetyClassification,
    ValidationOutcome,
)


class LLMProvider(Protocol):
    """Protocol defining LLM operations required across the LangGraph agent."""

    def classify_safety(
        self,
        user_message: str,
        recent_context: list[dict[str, Any]] | None = None,
    ) -> SafetyClassification:
        """Evaluate if user request crosses into clinical advice/diagnosis."""
        ...

    def understand_request(
        self,
        user_message: str,
        context_summary: dict[str, Any] | None = None,
    ) -> RequestPlan:
        """Infer intent, extract entities, references, and create typed execution plan."""
        ...

    def generate_clarification(
        self,
        target: str | None,
        reason: str | None,
        options: list[str] | None = None,
        language: str = "en",
    ) -> str:
        """Generate a single focused, natural clarification question."""
        ...

    def compose_response(
        self,
        evidence_bundle: dict[str, Any],
    ) -> ResponseDraft:
        """Compose final natural-language response synthesized strictly from trusted evidence."""
        ...

    def validate_response(
        self,
        draft: str,
        evidence_bundle: dict[str, Any],
    ) -> ValidationOutcome:
        """Validate that draft response contains no hallucinations, ungrounded prices, or fake actions."""
        ...
