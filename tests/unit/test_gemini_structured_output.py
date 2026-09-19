from __future__ import annotations

import json

from app.agent.llm.gemini_provider import GeminiProvider
from app.agent.schemas import AgentIntent, SafetyCategory


def test_understand_request_normalizes_bounded_json_shape_drift(monkeypatch) -> None:
    provider = GeminiProvider(api_key="test-key")
    payload = {
        "primary_intent": "TEST_PRICE",
        "requested_information": "price",
        "entities": {"test_query": "CBC"},
        "references": {},
        "ambiguities": None,
        "requires_structured_data": True,
        "requires_rag": False,
        "requires_customer_history": False,
        "action_intent": False,
        "needs_clarification": False,
        "clarification_target": None,
        "language": "English",
    }

    monkeypatch.setattr(
        provider,
        "_call_generate_content",
        lambda *args, **kwargs: json.dumps(payload),
    )

    plan = provider.understand_request("How much is CBC?")

    assert plan.primary_intent == AgentIntent.TEST_PRICE
    assert plan.requested_information == ["price"]
    assert plan.references == []
    assert plan.ambiguities == []
    assert plan.action_intent is None
    assert plan.language == "en"
    assert plan.requires_structured_data is True
    assert plan.needs_clarification is False


def test_understand_request_keeps_nonempty_invalid_reference_object_strict(monkeypatch) -> None:
    provider = GeminiProvider(api_key="test-key")
    payload = {
        "primary_intent": "TEST_PRICE",
        "requested_information": ["price"],
        "entities": {"test_query": "CBC"},
        "references": {"unexpected": "shape"},
        "ambiguities": [],
        "requires_structured_data": True,
        "requires_rag": False,
        "requires_customer_history": False,
        "action_intent": None,
        "needs_clarification": False,
        "clarification_target": None,
        "language": "en",
    }

    monkeypatch.setattr(
        provider,
        "_call_generate_content",
        lambda *args, **kwargs: json.dumps(payload),
    )

    plan = provider.understand_request("How much is CBC?")

    assert plan.primary_intent == AgentIntent.UNKNOWN_AMBIGUOUS
    assert plan.needs_clarification is True
    assert plan.clarification_target == "request_meaning"


def test_safety_prompt_distinguishes_catalog_search_from_clinical_recommendation(monkeypatch) -> None:
    provider = GeminiProvider(api_key="test-key")
    captured: dict[str, str] = {}

    def fake_call(*args, **kwargs):
        captured["system_instruction"] = kwargs["system_instruction"]
        return json.dumps(
            {
                "category": "SAFE_OPERATIONAL",
                "confidence": 0.99,
                "reason": "Catalog search without symptoms or clinical judgment.",
            }
        )

    monkeypatch.setattr(provider, "_call_generate_content", fake_call)

    classification = provider.classify_safety("I need a thyroid-related test.")

    assert classification.category == SafetyCategory.SAFE_OPERATIONAL
    prompt = captured["system_instruction"]
    assert "clinical judgment" in prompt.lower()
    assert "thyroid-related test" in prompt
    assert "non-clinical out-of-domain" in prompt
    assert "symptoms/clinical context" in prompt
