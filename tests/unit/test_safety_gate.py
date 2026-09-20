"""Unit tests for safety_gate node and healthcare boundaries."""

from __future__ import annotations

from app.agent.llm.factory import set_override_llm_provider
from app.agent.llm.fake import FakeLLMProvider
from app.agent.nodes.safety_gate import safety_gate
from app.agent.schemas import SafetyCategory, SafetyClassification
from app.agent.state import create_initial_state


def teardown_function() -> None:
    """Clear provider override after each test."""
    set_override_llm_provider(None)


def test_safety_gate_operational_inquiry_passes() -> None:
    """Safe operational requests pass through smoothly."""
    provider = FakeLLMProvider(
        canned_safety=SafetyClassification(
            category=SafetyCategory.SAFE_OPERATIONAL,
            confidence=1.0,
            reason="Operational lab inquiry",
        )
    )
    set_override_llm_provider(provider)

    state = create_initial_state("session-1", "How much does a CBC test cost?")
    update = safety_gate(state)

    assert update["is_safe"] is True
    assert update["safety_classification"]["category"] == SafetyCategory.SAFE_OPERATIONAL.value
    assert "response_goal" not in update


def test_safety_gate_blocks_result_interpretation() -> None:
    """Clinical interpretation of lab values is blocked."""
    provider = FakeLLMProvider(
        canned_safety=SafetyClassification(
            category=SafetyCategory.RESULT_INTERPRETATION,
            confidence=0.98,
            reason="User asking for diagnosis on glucose 250",
        )
    )
    set_override_llm_provider(provider)

    state = create_initial_state("session-2", "My glucose is 250, do I have diabetes?")
    update = safety_gate(state)

    assert update["is_safe"] is False
    assert update["response_goal"] == "SAFE_BOUNDARY"
    assert update["safety_classification"]["category"] == SafetyCategory.RESULT_INTERPRETATION.value


def test_safety_gate_blocks_medication_advice() -> None:
    """Medication prescription inquiries are blocked."""
    provider = FakeLLMProvider(
        canned_safety=SafetyClassification(
            category=SafetyCategory.MEDICATION_ADVICE,
            confidence=0.99,
            reason="User asking what medicine to take",
        )
    )
    set_override_llm_provider(provider)

    state = create_initial_state("session-3", "My TSH is high, what medicine should I take?")
    update = safety_gate(state)

    assert update["is_safe"] is False
    assert update["response_goal"] == "SAFE_BOUNDARY"
    assert update["safety_classification"]["category"] == SafetyCategory.MEDICATION_ADVICE.value


def test_safety_gate_blocks_symptom_based_test_recommendation() -> None:
    """Prescribing tests based on subjective symptoms is blocked."""
    provider = FakeLLMProvider(
        canned_safety=SafetyClassification(
            category=SafetyCategory.SYMPTOM_BASED_TEST_RECOMMENDATION,
            confidence=0.99,
            reason="User requesting test based on dizziness",
        )
    )
    set_override_llm_provider(provider)

    state = create_initial_state("session-4", "عندي دوخة شديدة أعمل تحليل إيه؟")
    update = safety_gate(state)

    assert update["is_safe"] is False
    assert update["response_goal"] == "SAFE_BOUNDARY"
    assert (
        update["safety_classification"]["category"]
        == SafetyCategory.SYMPTOM_BASED_TEST_RECOMMENDATION.value
    )


def test_safety_gate_deterministic_fail_safe_catches_missed_clinical_terms() -> None:
    """Deterministic fail-safe catches critical symptoms even if LLM misclassifies as safe."""
    # LLM incorrectly returns SAFE_OPERATIONAL
    provider = FakeLLMProvider(
        canned_safety=SafetyClassification(
            category=SafetyCategory.SAFE_OPERATIONAL,
            confidence=0.5,
            reason="False safe classification",
        )
    )
    set_override_llm_provider(provider)

    state = create_initial_state("session-5", "I feel dizzy what test should I do?")
    update = safety_gate(state)

    # Fail-safe must intervene and mark unsafe
    assert update["is_safe"] is False
    assert update["response_goal"] == "SAFE_BOUNDARY"
    assert "Deterministic fail-safe" in update["safety_reason"]
