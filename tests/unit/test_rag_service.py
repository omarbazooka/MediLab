"""Unit tests for RAGService orchestration, bounded retry, and degraded mode."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.rag.embeddings import DeterministicFakeEmbeddingProvider
from app.rag.service import RAGRetrievalError, RAGService
from app.rag.types import LexicalCandidate, RetrievalOutcome, SemanticCandidate


def _make_sem_cand(chunk_id: int, dist: float = 0.25) -> SemanticCandidate:
    return SemanticCandidate(
        chunk_id=chunk_id,
        document_id=1,
        document_title="Cancellation Policy",
        document_category="Policies",
        document_version=1,
        chunk_index=0,
        content="Appointments can be cancelled up to 2 hours in advance.",
        cosine_distance=dist,
        semantic_rank=1,
    )


def _make_lex_cand(chunk_id: int, score: float = 0.8) -> LexicalCandidate:
    return LexicalCandidate(
        chunk_id=chunk_id,
        document_id=1,
        document_title="Cancellation Policy",
        document_category="Policies",
        document_version=1,
        chunk_index=0,
        content="Appointments can be cancelled up to 2 hours in advance.",
        fts_score=score,
        lexical_rank=1,
    )


def test_rag_service_good_first_retrieval_stops_at_attempt_one() -> None:
    repo = MagicMock()
    repo.search_semantic.return_value = [_make_sem_cand(1, dist=0.2)]
    repo.search_lexical.return_value = [_make_lex_cand(1, score=0.9)]

    service = RAGService(
        repository=repo,
        embedding_provider=DeterministicFakeEmbeddingProvider(),
    )

    result = service.retrieve("How can I cancel my appointment?")
    assert result.outcome == RetrievalOutcome.GOOD.value
    assert result.attempt_count == 1
    assert result.diagnostics.retry_used is False
    assert len(result.final_chunks) == 1
    assert result.final_chunks[0].chunk_id == 1
    assert repo.search_semantic.call_count == 1


def test_rag_service_weak_retrieval_triggers_exactly_one_retry() -> None:
    repo = MagicMock()
    # Attempt 1: Weak match (cosine distance 0.51, weak lexical match -> WEAK_RETRY)
    # Attempt 2: Strong match found on retry
    repo.search_semantic.side_effect = [
        [_make_sem_cand(1, dist=0.51)],
        [_make_sem_cand(1, dist=0.20)],
    ]
    repo.search_lexical.side_effect = [
        [_make_lex_cand(1, score=0.04)],
        [_make_lex_cand(1, score=0.9)],
    ]

    service = RAGService(
        repository=repo,
        embedding_provider=DeterministicFakeEmbeddingProvider(),
    )

    result = service.retrieve("cancel slot")
    assert result.attempt_count == 2
    assert result.diagnostics.retry_used is True
    assert repo.search_semantic.call_count == 2
    assert repo.search_lexical.call_count == 2


def test_rag_service_second_weak_retrieval_does_not_loop() -> None:
    repo = MagicMock()
    # Both attempts produce weak match (dist=0.51, weak lexical score -> WEAK_RETRY)
    repo.search_semantic.return_value = [_make_sem_cand(1, dist=0.51)]
    repo.search_lexical.return_value = [_make_lex_cand(1, score=0.04)]

    service = RAGService(
        repository=repo,
        embedding_provider=DeterministicFakeEmbeddingProvider(),
    )

    result = service.retrieve("borderline vague query")
    # Strict invariant: exactly 2 attempts total, never loops again!
    assert result.attempt_count == 2
    assert repo.search_semantic.call_count == 2
    assert result.outcome == RetrievalOutcome.WEAK_RETRY.value


def test_rag_service_ambiguous_query_stops_before_search() -> None:
    repo = MagicMock()
    service = RAGService(
        repository=repo,
        embedding_provider=DeterministicFakeEmbeddingProvider(),
    )

    result = service.retrieve("Can I eat food before it?", context=None)
    assert result.outcome == RetrievalOutcome.AMBIGUOUS_USER_QUERY.value
    assert result.attempt_count == 1
    assert repo.search_semantic.call_count == 0
    assert repo.search_lexical.call_count == 0


def test_rag_service_degraded_mode_when_semantic_fails() -> None:
    repo = MagicMock()
    repo.search_lexical.return_value = [_make_lex_cand(1, score=0.9)]

    mock_provider = MagicMock()
    mock_provider.embed_query.side_effect = RuntimeError("External Jina API timed out")

    service = RAGService(
        repository=repo,
        embedding_provider=mock_provider,
    )

    result = service.retrieve("Cancellation policy")
    assert result.degraded_mode is True
    assert len(result.final_chunks) == 1
    assert result.final_chunks[0].chunk_id == 1
    assert result.outcome == RetrievalOutcome.GOOD.value


def test_rag_service_degraded_mode_when_lexical_fails() -> None:
    repo = MagicMock()
    repo.search_semantic.return_value = [_make_sem_cand(1, dist=0.25)]
    repo.search_lexical.side_effect = RuntimeError("PostgreSQL FTS connection dropped")

    service = RAGService(
        repository=repo,
        embedding_provider=DeterministicFakeEmbeddingProvider(),
    )

    result = service.retrieve("Cancellation policy")
    assert result.degraded_mode is True
    assert len(result.final_chunks) == 1
    assert result.final_chunks[0].chunk_id == 1


def test_rag_service_raises_when_both_retrieval_arms_fail() -> None:
    repo = MagicMock()
    repo.search_lexical.side_effect = RuntimeError("DB down")

    mock_provider = MagicMock()
    mock_provider.embed_query.side_effect = RuntimeError("API down")

    service = RAGService(
        repository=repo,
        embedding_provider=mock_provider,
    )

    with pytest.raises(RAGRetrievalError, match="Both semantic and lexical retrieval arms failed"):
        service.retrieve("Any query")


def test_rag_service_raises_embedding_config_error_when_provider_misconfigured() -> None:
    from app.rag.embeddings import EmbeddingConfigError

    mock_provider = MagicMock()
    mock_provider.embed_query.side_effect = EmbeddingConfigError("JINA_API_KEY is missing")

    service = RAGService(
        repository=MagicMock(),
        embedding_provider=mock_provider,
    )

    with pytest.raises(EmbeddingConfigError, match="JINA_API_KEY is missing"):
        service.retrieve("Any query")
