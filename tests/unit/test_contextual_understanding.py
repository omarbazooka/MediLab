"""Tests for the bounded context supplied to the LLM understanding pass."""

from __future__ import annotations

from flask import Flask

from app.agent.llm.factory import set_override_llm_provider
from app.agent.llm.fake import FakeLLMProvider
from app.agent.nodes.understand_request import understand_request
from app.agent.schemas import AgentIntent, RequestPlan
from app.agent.state import create_initial_state


def test_understanding_receives_bounded_relevant_context_without_contact_identifiers(app: Flask) -> None:
    captured: dict[str, object] = {}
    fake = FakeLLMProvider()

    def handler(message: str, context: dict | None) -> RequestPlan:
        captured["message"] = message
        captured["context"] = context
        return RequestPlan(primary_intent=AgentIntent.TEST_PRICE, requires_structured_data=True)

    fake.understanding_handler = handler

    with app.app_context():
        set_override_llm_provider(fake)
        try:
            state = create_initial_state("contextual-1", "How much is it now?")
            state["selected_test_id"] = 7
            state["selected_test_code"] = "TSH"
            state["selected_test_name"] = "Thyroid Stimulating Hormone (TSH)"
            state["recent_messages"] = [
                {"role": "user", "content": "Tell me about TSH"},
                {"role": "assistant", "content": "Here are the verified details."},
            ]
            state["customer_id"] = 99
            state["customer_context"] = {
                "customer_id": 99,
                "customer_name": "Private Name",
                "customer_phone": "+201000000000",
                "recent_bookings": [
                    {
                        "booking_reference": "MED-CTX-1",
                        "scheduled_date": "2026-09-18",
                        "scheduled_time": "10:00",
                        "status": "CONFIRMED",
                        "visit_type": "BRANCH",
                        "branch_name": "Maadi",
                        "items": ["TSH"],
                        "total_price": "220.00 EGP",
                    }
                ],
                "latest_service": "TSH",
                "has_active_booking": True,
                "has_cancellations": False,
            }

            understand_request(state)
        finally:
            set_override_llm_provider(None)

    context = captured["context"]
    assert isinstance(context, dict)
    assert context["selected_test_code"] == "TSH"
    assert context["selected_test"]["name"] == "Thyroid Stimulating Hormone (TSH)"
    assert len(context["recent_conversation"]) == 2
    assert context["customer_history_summary"]["recent_bookings"][0]["booking_reference"] == "MED-CTX-1"
    assert "customer_phone" not in str(context)
    assert "Private Name" not in str(context)
