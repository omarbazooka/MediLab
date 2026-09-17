"""Unit tests for embedding providers, Jina API integration, and mock transports."""

from __future__ import annotations

import json

import httpx
import pytest

from app.rag.embeddings import (
    DeterministicFakeEmbeddingProvider,
    EmbeddingConfigError,
    EmbeddingProviderError,
    JinaEmbeddingProvider,
)


def test_missing_api_key_raises_config_error() -> None:
    provider = JinaEmbeddingProvider(api_key="")
    with pytest.raises(EmbeddingConfigError, match="Jina API key is not configured"):
        provider.embed_query("fasting instructions")


def test_jina_provider_sends_retrieval_query_and_384_dimensions() -> None:
    captured_request: dict = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.read())

        # Return mock 384-dimensional vector
        mock_embedding = [0.05] * 384
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": mock_embedding}]},
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    provider = JinaEmbeddingProvider(
        api_key="mock-secret-jina-key-12345",
        http_client=client,
    )

    vector = provider.embed_query("Do I need to fast?")
    assert len(vector) == 384
    assert captured_request["body"]["task"] == "retrieval.query"
    assert captured_request["body"]["dimensions"] == 384
    assert captured_request["body"]["model"] == "jina-embeddings-v3"
    assert captured_request["body"]["input"] == ["Do I need to fast?"]
    assert captured_request["headers"]["authorization"] == "Bearer mock-secret-jina-key-12345"


def test_jina_provider_sends_retrieval_passage_for_documents() -> None:
    captured_request: dict = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_request["body"] = json.loads(request.read())
        mock_embeddings = [[0.1] * 384, [0.2] * 384]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": mock_embeddings[1]},
                    {"index": 0, "embedding": mock_embeddings[0]},
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    provider = JinaEmbeddingProvider(
        api_key="mock-secret-key",
        http_client=client,
    )

    passages = ["Passage 1 content", "Passage 2 content"]
    vectors = provider.embed_documents(passages)
    assert len(vectors) == 2
    # Verify order preservation despite returned index permutation
    assert vectors[0] == [0.1] * 384
    assert vectors[1] == [0.2] * 384
    assert captured_request["body"]["task"] == "retrieval.passage"
    assert captured_request["body"]["dimensions"] == 384


def test_jina_provider_rejects_non_384_dimension() -> None:
    def mock_handler(_request: httpx.Request) -> httpx.Response:
        # Provider unexpectedly returns 512 dimensions
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1] * 512}]},
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)
    provider = JinaEmbeddingProvider(api_key="mock-key", http_client=client)

    with pytest.raises(EmbeddingProviderError, match="expected 384, got 512"):
        provider.embed_query("test query")


def test_jina_provider_masks_secrets_on_http_error() -> None:
    secret_token = "secret-super-sensitive-token-xyz"

    def mock_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text=f"Unauthorized: token {secret_token} rejected by gateway",
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)
    provider = JinaEmbeddingProvider(api_key=secret_token, http_client=client)

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed_query("test query")

    # Ensure secret token is NEVER exposed in the exception message
    assert secret_token not in str(exc_info.value)


def test_deterministic_fake_provider() -> None:
    fake = DeterministicFakeEmbeddingProvider(dimension=384)
    v1 = fake.embed_query("Fasting for lipid profile")
    v2 = fake.embed_query("Fasting for lipid profile")
    v3 = fake.embed_query("Completely different topic")

    assert len(v1) == 384
    assert v1 == v2
    assert v1 != v3


def test_get_embedding_provider_factory_jina_valid() -> None:
    from app.rag.embeddings import get_embedding_provider

    provider = get_embedding_provider(
        {
            "EMBEDDING_PROVIDER": "jina",
            "JINA_API_KEY": "test-key-123",
            "EMBEDDING_MODEL": "jina-embeddings-v3",
            "EMBEDDING_DIMENSION": 384,
        }
    )
    assert isinstance(provider, JinaEmbeddingProvider)
    assert provider.api_key == "test-key-123"
    assert provider.dimension == 384


def test_get_embedding_provider_factory_missing_jina_key_raises() -> None:
    from app.rag.embeddings import get_embedding_provider

    with pytest.raises(EmbeddingConfigError, match="JINA_API_KEY is required"):
        get_embedding_provider(
            {
                "EMBEDDING_PROVIDER": "jina",
                "JINA_API_KEY": "",
            }
        )


def test_get_embedding_provider_factory_fake() -> None:
    from app.rag.embeddings import get_embedding_provider

    provider = get_embedding_provider({"EMBEDDING_PROVIDER": "fake", "EMBEDDING_DIMENSION": 384})
    assert isinstance(provider, DeterministicFakeEmbeddingProvider)
    assert provider.dimension == 384


def test_get_embedding_provider_factory_unsupported_provider_raises() -> None:
    from app.rag.embeddings import get_embedding_provider

    with pytest.raises(EmbeddingConfigError, match="Unsupported EMBEDDING_PROVIDER"):
        get_embedding_provider({"EMBEDDING_PROVIDER": "unsupported_xyz"})
