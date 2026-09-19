"""Unit tests for response_validator node."""

from __future__ import annotations

from app.agent.nodes.response_validator import response_validator
from app.agent.state import create_initial_state


def test_response_validator_accepts_grounded_response() -> None:
    """A safe, fact-based response passes validation."""
    state = create_initial_state("session-val-1", "How much is CBC?")
    state["response_draft"] = "Complete Blood Count (CBC) is priced at 250.00 EGP."
    state["structured_result"] = {"test": {"name": "CBC", "price": "250.00 EGP"}}

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is True
    assert update["final_response"] == "Complete Blood Count (CBC) is priced at 250.00 EGP."


def test_response_validator_accepts_grounded_price_from_nested_results() -> None:
    """Verified prices in list/search result structures are accepted recursively."""
    state = create_initial_state("session-val-list", "Show packages")
    state["response_draft"] = "The package is 980.00 EGP."
    state["structured_result"] = {
        "packages": [{"name": "Vitality & Wellness Panel", "price": "980.00 EGP"}]
    }

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is True


def test_response_validator_blocks_fake_booking_confirmation() -> None:
    """Falsely claiming a confirmed booking without action result is caught and repaired."""
    state = create_initial_state("session-val-2", "Book branch appointment")
    state["response_draft"] = "Great, your booking is confirmed for tomorrow!"
    state["action_result"] = None

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is False
    assert any("falsely claims action success" in r for r in update["validation_result"]["reasons"])
    assert "booking is confirmed" not in update["final_response"].lower()


def test_response_validator_blocks_success_claim_for_failed_action_result() -> None:
    """A non-null failed action result never authorizes a customer-facing success claim."""
    state = create_initial_state("session-val-failed-action", "Cancel booking")
    state["response_draft"] = "Your booking was cancelled successfully."
    state["action_result"] = {"success": False, "committed": False, "error": "conflict"}

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is False
    assert "cancelled successfully" not in update["final_response"].lower()


def test_response_validator_allows_claim_with_explicit_committed_success() -> None:
    """Phase 4 may authorize success only with explicit committed-success truth."""
    state = create_initial_state("session-val-success-action", "Cancel booking")
    state["response_draft"] = "Your booking was cancelled successfully."
    state["action_result"] = {
        "success": True,
        "committed": True,
        "booking_reference": "MED-123",
    }

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is True
    assert update["final_response"] == "Your booking was cancelled successfully."


def test_response_validator_blocks_clinical_diagnosis() -> None:
    """Prohibited medical diagnosis is caught and repaired."""
    state = create_initial_state("session-val-3", "My glucose is 250")
    state["response_draft"] = "Based on glucose 250, you have diabetes."

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is False
    assert any("prohibited medical diagnosis" in r for r in update["validation_result"]["reasons"])
    assert "qualified healthcare professional" in update["final_response"]


def test_response_validator_blocks_ungrounded_price() -> None:
    """A price absent from verified SQL evidence must invalidate and repair the draft."""
    state = create_initial_state("session-val-4", "What is TSH?")
    state["response_draft"] = "TSH costs 999.00 EGP."
    state["structured_result"] = {"test": {"name": "TSH", "price": "220.00 EGP"}}

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is False
    assert any("999.00" in r and "not present" in r for r in update["validation_result"]["reasons"])
    assert "999.00" not in update["final_response"]


def test_response_validator_blocks_price_without_structured_evidence() -> None:
    """LLM/RAG text may not introduce business prices when SQL evidence is absent."""
    state = create_initial_state("session-val-no-evidence", "How much is this?")
    state["response_draft"] = "It costs 500 EGP."
    state["structured_result"] = None

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is False
    assert "500" not in update["final_response"]


def test_response_validator_empty_draft_repaired() -> None:
    """Empty draft response is caught and replaced with polite fallback."""
    state = create_initial_state("session-val-5", "Hello")
    state["response_draft"] = "   "

    update = response_validator(state)

    assert update["validation_result"]["is_valid"] is False
    assert update["final_response"] != ""
    assert "I apologize" in update["final_response"]
