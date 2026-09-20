from __future__ import annotations

import pytest

from scripts.eval_phase3_gemini_live import (
    LIVE_SUBSET_IDS,
    _fact_present,
    _validate_disposable_database,
)


def test_live_gemini_subset_includes_real_action_boundary_cases() -> None:
    assert {"case_030", "case_031", "case_032"}.issubset(set(LIVE_SUBSET_IDS))


def test_live_gemini_eval_rejects_supabase_test_database() -> None:
    with pytest.raises(RuntimeError, match="Supabase"):
        _validate_disposable_database(
            "postgresql+psycopg://postgres:secret@db.example.supabase.co:5432/postgres",
            "",
        )


def test_live_gemini_eval_rejects_application_database_equality() -> None:
    url = "postgresql+psycopg://postgres:postgres@localhost:5432/medilab"
    with pytest.raises(RuntimeError, match="must not equal"):
        _validate_disposable_database(url, url)


def test_live_fact_matching_accepts_equivalent_clinical_boundary_wording() -> None:
    response = (
        "MediLab does not provide clinical diagnoses. "
        "Please consult a qualified healthcare professional."
    ).lower()

    assert _fact_present("cannot diagnose", response)
    assert _fact_present("doctor", response)
    assert _fact_present("physician", response)
