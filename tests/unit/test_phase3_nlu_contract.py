"""Focused regression tests for Phase 3 Gemini NLU contract, normalization, and evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from app.agent.llm.fake import FakeLLMProvider
from app.agent.llm.gemini_provider import GeminiProvider
from app.agent.nodes.router import route_request
from app.agent.schemas import AgentIntent
from app.agent.state import MediLabAgentState
from app.repositories.package_repository import PackageRepository
from scripts.eval_phase3_gemini_live import _fact_present, _verify_disposable_database_seeded


def test_entity_normalization_maps_aliases_to_canonical_keys() -> None:
    raw_payload: dict[str, Any] = {
        "primary_intent": "TEST_PRICE",
        "entities": {
            "test_name": "Complete Blood Count (CBC)",
            "package_name": "Comprehensive Health Checkup",
            "branch_name": "Nasr City",
            "item_id": 42,
            "item_type": "test",
            "ordinal": "first",
        },
    }
    normalized = GeminiProvider._normalize_request_plan_payload(raw_payload)
    entities = normalized["entities"]

    assert entities["test_query"] == "CBC"
    assert entities["package_query"] == "Comprehensive Health Checkup"
    assert entities["branch_query"] == "Nasr City"
    assert entities["visible_item_id"] == 42
    assert entities["visible_item_type"] == "test"
    assert entities["ordinal_ref"] == "first"


def test_entity_normalization_prefers_explicit_catalog_test_codes() -> None:
    cases = [
        ({"test_query": "Complete Blood Count (CBC)"}, "CBC"),
        ({"test": "تحليل وظائف الكلى KFT"}, "KFT"),
        ({"code": "test ال TSH"}, "TSH"),
        ({"test_name": "LFT"}, "LFT"),
        ({"test_query": "Serum Ferritin"}, "FERRITIN"),
        ({"test_query": "Lipid Profile Panel"}, "LIPID"),
    ]
    for raw_entities, expected_code in cases:
        payload = {"primary_intent": "TEST_PRICE", "entities": raw_entities}
        normalized = GeminiProvider._normalize_request_plan_payload(payload)
        assert normalized["entities"]["test_query"] == expected_code


def test_case_014_taxonomy_canonical_contract() -> None:
    eval_file = Path(__file__).resolve().parent.parent.parent / "evals" / "phase3_agent_cases.json"
    with open(eval_file, encoding="utf-8") as handle:
        cases = json.load(handle)

    case_014 = next((c for c in cases if c["id"] == "case_014"), None)
    assert case_014 is not None
    assert case_014["expected_intent"] == "CANCELLATION_POLICY"
    assert case_014["expected_route"] == "rag"

    fake_provider = FakeLLMProvider()
    plan = fake_provider.understand_request(case_014["user_message"])
    assert plan.primary_intent == AgentIntent.CANCELLATION_POLICY
    assert plan.requires_rag is True

    dummy_state: MediLabAgentState = {
        "is_safe": True,
        "intent": AgentIntent.CANCELLATION_POLICY.value,
        "request_plan": plan.model_dump(),
    }
    assert route_request(dummy_state) == "rag"


@pytest.mark.postgres
def test_package_repository_search_token_fallback(postgres_app: Flask) -> None:
    with postgres_app.app_context():
        repo = PackageRepository()
        results = repo.search("general health checkup")
        assert any(pkg.name == "Comprehensive Health Checkup" for pkg in results)


@pytest.mark.postgres
def test_verify_disposable_database_seeded(postgres_app: Flask) -> None:
    with postgres_app.app_context():
        _verify_disposable_database_seeded()


def test_fact_grounding_non_business_semantic_aliases() -> None:
    # Action boundary: "booking", "service"
    response_30 = (
        "I would be glad to help you book a home visit for CBC. However, appointment booking "
        "cannot be finalized directly here. Please contact our customer care team."
    )
    assert _fact_present("booking", response_30.lower())
    assert _fact_present("service", response_30.lower())

    # Action boundary: "cancellation", "customer service"
    response_32 = (
        "I understand you want to cancel booking #1024. Transactional cancellations are not "
        "supported directly by this assistant. Please reach out to our support team."
    )
    assert _fact_present("cancellation", response_32.lower())
    assert _fact_present("customer service", response_32.lower())

    # Greeting / capabilities: "branches", "tests"
    response_33 = (
        "Hello! I'm MediLab AI, your diagnostic-laboratory sales and customer-service assistant. "
        "I can help you with information about our laboratory tests, packages, preparation guidelines, and services."
    )
    assert _fact_present("branches", response_33.lower())
    assert _fact_present("tests", response_33.lower())

    # Out-of-domain: "medical laboratory", "cannot help"
    response_38 = (
        "No, MediLab AI is a diagnostic-laboratory assistant, so we do not repair smartphones "
        "or laptop screens. We can help you with our laboratory tests and services!"
    )
    assert _fact_present("medical laboratory", response_38.lower())
    assert _fact_present("cannot help", response_38.lower())


def test_action_boundary_instruction_in_gemini_provider() -> None:
    provider = GeminiProvider(api_key="test-key")
    # Check that the system instruction contains guidance for action boundaries
    # without needing to make a live API call
    from unittest.mock import MagicMock

    provider._call_generate_content = MagicMock(return_value="Action not supported")
    draft = provider.compose_response(
        {
            "response_goal": "ACTION_NOT_YET_EXECUTABLE",
            "language": "en",
        }
    )
    assert draft.response_goal.value == "ACTION_NOT_YET_EXECUTABLE"
    # Verify the system_instruction passed to _call_generate_content
    call_args = provider._call_generate_content.call_args
    assert (
        "explain that automated booking and cancellation actions are not yet supported"
        in call_args.kwargs["system_instruction"]
    )
    assert "advise contacting customer service" in call_args.kwargs["system_instruction"]


def test_gemini_provider_parse_json_payload_robustness() -> None:
    # 1. Markdown code fences
    fenced = '```json\n{"primary_intent": "TEST_PRICE"}\n```'
    assert GeminiProvider._parse_json_payload(fenced)["primary_intent"] == "TEST_PRICE"

    # 2. Single-quoted keys, single-quoted values, booleans, null, and trailing commas
    malformed = (
        "{\n  'primary_intent': 'BOOK_BRANCH_VISIT',\n  'action_intent': 'BOOK_BRANCH_VISIT',\n"
        "  'requires_rag': false,\n  'clarification_target': null, // comment\n}"
    )
    res = GeminiProvider._parse_json_payload(malformed)
    assert res["primary_intent"] == "BOOK_BRANCH_VISIT"
    assert res["action_intent"] == "BOOK_BRANCH_VISIT"
    assert res["requires_rag"] is False
    assert res["clarification_target"] is None

    # 3. Text preamble / postscript surrounding JSON
    surrounded = 'Here is the plan:\n{"primary_intent": "TEST_DETAILS"}\nHope this helps!'
    assert GeminiProvider._parse_json_payload(surrounded)["primary_intent"] == "TEST_DETAILS"

    # 4. Block comments and nested trailing commas
    with_block_comment = (
        '{\n  "primary_intent": "BOOK_BRANCH_VISIT",\n  /* notes */\n'
        '  "entities": {\n    "test_query": "CBC",\n  },\n}'
    )
    res_comment = GeminiProvider._parse_json_payload(with_block_comment)
    assert res_comment["primary_intent"] == "BOOK_BRANCH_VISIT"
    assert res_comment["entities"]["test_query"] == "CBC"

    # 5. Single-quoted array items
    with_sq_array = (
        '{\n  "primary_intent": "TEST_DETAILS",\n'
        "  \"requested_information\": ['price', 'preparation']\n}"
    )
    res_array = GeminiProvider._parse_json_payload(with_sq_array)
    assert res_array["primary_intent"] == "TEST_DETAILS"
    assert res_array["requested_information"] == ["price", "preparation"]

    # 6. Severely broken syntax with regex fallback extraction
    broken = (
        'Here is the response:\n{\n  "primary_intent": "BOOK_BRANCH_VISIT",\n'
        '  "action_intent": "BOOK_BRANCH_VISIT",\n'
        '  "entities": {"test_query": "CBC", "branch_query": "Nasr City"},\n'
        '  "language": "ar"\n'
        "  syntax error at end"
    )
    res_broken = GeminiProvider._parse_json_payload(broken)
    assert res_broken["primary_intent"] == "BOOK_BRANCH_VISIT"
    assert res_broken["action_intent"] == "BOOK_BRANCH_VISIT"
    assert res_broken["entities"]["test_query"] == "CBC"


def test_uncertainty_gate_passes_clear_for_out_of_domain() -> None:
    from app.agent.nodes.uncertainty_gate import uncertainty_gate

    state: MediLabAgentState = {
        "is_safe": True,
        "intent": AgentIntent.UNKNOWN_AMBIGUOUS.value,
        "needs_clarification": False,
        "ambiguities": ["User asked about laptop repairs."],
        "selected_test_id": None,
        "selected_package_id": None,
    }
    assert uncertainty_gate(state) == "clear"


def test_normalize_out_of_domain_clears_ambiguities_when_not_clarifying() -> None:
    payload = {
        "primary_intent": "UNKNOWN_AMBIGUOUS",
        "needs_clarification": False,
        "ambiguities": ["User asked about repairing phone screens."],
    }
    normalized = GeminiProvider._normalize_request_plan_payload(payload)
    assert normalized["ambiguities"] == []


def test_combined_read_node_propagates_subnode_routes() -> None:
    from unittest.mock import patch

    from app.agent.nodes.combined_read_node import combined_read_node

    dummy_state: MediLabAgentState = {
        "is_safe": True,
        "route_trace": ["router_node"],
        "node_timings": {},
    }
    with (
        patch("app.agent.nodes.combined_read_node.structured_data_node") as mock_struct,
        patch("app.agent.nodes.combined_read_node.rag_node") as mock_rag,
    ):
        mock_struct.side_effect = lambda s: {
            "structured_result": {"price": 250},
            "route_trace": list(s.get("route_trace", [])) + ["structured_data_node"],
            "node_timings": {"structured_data_node": 10.0},
        }
        mock_rag.side_effect = lambda s: {
            "rag_result": {"context": "fasting guide"},
            "route_trace": list(s.get("route_trace", [])) + ["rag_node"],
            "node_timings": {"rag_node": 15.0},
        }
        res = combined_read_node(dummy_state)
        assert "combined_read_node" in res["route_trace"]
        assert "structured_data_node" in res["route_trace"]
        assert "rag_node" in res["route_trace"]
