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
