"""Unit tests for understand_request node and LLM RequestPlan parsing."""

from __future__ import annotations

from app.agent.llm.factory import set_override_llm_provider
from app.agent.llm.fake import FakeLLMProvider
from app.agent.nodes.understand_request import understand_request
from app.agent.schemas import AgentIntent, RequestPlan
from app.agent.state import create_initial_state


def teardown_function() -> None:
    set_override_llm_provider(None)


def test_understand_request_structured_schema() -> None:
    """Ensure LLM output strictly parses into validated RequestPlan."""
    plan = RequestPlan(
        primary_intent=AgentIntent.TEST_DETAILS,
        requested_information=["price", "definition"],
        entities={"test_query": "CBC"},
        requires_structured_data=True,
        requires_rag=False,
        language="en",
    )
    provider = FakeLLMProvider(canned_plan=plan)
    set_override_llm_provider(provider)

    state = create_initial_state("session-1", "How much is CBC?")
    update = understand_request(state)

    assert update["intent"] == AgentIntent.TEST_DETAILS.value
    assert update["entities"]["test_query"] == "CBC"
    assert update["request_plan"]["requires_structured_data"] is True


def test_understand_request_arabic_paraphrase() -> None:
    """Handles colloquial and standard Arabic phrasing without keyword rules."""
    provider = FakeLLMProvider()
    set_override_llm_provider(provider)

    state = create_initial_state("session-2", "تمن تحليل الدم الكامل إيه؟")
    update = understand_request(state)

    assert update["language"] == "ar"
    assert update["intent"] in {AgentIntent.TEST_DETAILS.value, AgentIntent.TEST_PRICE.value}
    assert update["request_plan"]["requires_structured_data"] is True


def test_understand_request_mixed_language_and_combined_plan() -> None:
    """Handles mixed Arabic/English requesting both price and preparation."""
    provider = FakeLLMProvider()
    set_override_llm_provider(provider)

    state = create_initial_state("session-3", "تحليل TSH بكام ومحتاج صيام؟")
    update = understand_request(state)

    assert update["request_plan"]["requires_structured_data"] is True
    assert update["request_plan"]["requires_rag"] is True
    assert "TSH" in update["entities"].get("test_query", "")


def test_understand_request_unseen_english_paraphrase() -> None:
    """Handles unseen natural English queries."""
    provider = FakeLLMProvider()
    set_override_llm_provider(provider)

    state = create_initial_state(
        "session-4", "Could you tell me the cost and schedule for lipid profile panel?"
    )
    update = understand_request(state)

    assert update["request_plan"]["requires_structured_data"] is True
    assert "LIPID" in update["entities"].get("test_query", "")


def test_understand_request_handles_provider_error_gracefully() -> None:
    """Unexpected provider failure falls back gracefully to UNKNOWN_AMBIGUOUS."""
    provider = FakeLLMProvider()

    def faulty_handler(msg: str, ctx: dict | None) -> RequestPlan:
        raise RuntimeError("API timeout during intent parsing")

    provider.understanding_handler = faulty_handler
    set_override_llm_provider(provider)

    state = create_initial_state("session-5", "Some query")
    update = understand_request(state)

    assert update["intent"] == AgentIntent.UNKNOWN_AMBIGUOUS.value
    assert update["ambiguities"] == ["Request understanding unavailable."]
    assert update["needs_clarification"] is True
