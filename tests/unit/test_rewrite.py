"""Unit tests for context-aware query rewrite and ambiguity detection."""

from __future__ import annotations

from app.rag.rewrite import has_ambiguous_reference, rewrite_query


def test_standalone_unambiguous_query_unchanged() -> None:
    query = "What is the cancellation policy for home visits?"
    res = rewrite_query(query, context=None)
    assert res.status == "NORMAL"
    assert res.is_ambiguous is False
    assert res.rewritten_query == query


def test_english_pronoun_with_trusted_context_resolves() -> None:
    query = "Do I need fasting for it?"
    context = {"selected_test_name": "Lipid Profile Panel"}
    res = rewrite_query(query, context=context)
    assert res.status == "REWRITTEN"
    assert res.is_ambiguous is False
    assert "Lipid Profile Panel" in res.rewritten_query
    assert "Do I need fasting for it?" in res.rewritten_query


def test_english_pronoun_without_context_flags_ambiguous_do_not_guess() -> None:
    query = "Can I take water before it?"
    res = rewrite_query(query, context=None)
    assert res.status == "AMBIGUOUS_USER_QUERY"
    assert res.is_ambiguous is True
    assert res.rewritten_query == query


def test_arabic_ambiguous_reference_with_context_resolves() -> None:
    query = "هل التحليل ده محتاج صيام؟"
    context = {"selected_test_name": "تحليل السكر التراكمي"}
    res = rewrite_query(query, context=context)
    assert res.status == "REWRITTEN"
    assert res.is_ambiguous is False
    assert "تحليل السكر التراكمي" in res.rewritten_query


def test_arabic_ambiguous_reference_without_context_flags_ambiguous() -> None:
    query = "هل ده قبلها صيام؟"
    res = rewrite_query(query, context=None)
    assert res.status == "AMBIGUOUS_USER_QUERY"
    assert res.is_ambiguous is True


def test_has_ambiguous_reference_detection() -> None:
    assert has_ambiguous_reference("how much for it?") is True
    assert has_ambiguous_reference("does that require home collection?") is True
    assert has_ambiguous_reference("هل لازم قبله صيام؟") is True
    assert has_ambiguous_reference("سعر تحليل فيتامين د كام؟") is False
    assert has_ambiguous_reference("What is fasting time for FBS?") is False
