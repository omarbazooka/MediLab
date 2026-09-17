"""Embedding provider abstraction and Jina AI implementation for MediLab AI."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol, runtime_checkable

import httpx

logger = logging.getLogger("medilab.rag.embeddings")


class EmbeddingError(Exception):
    """Base exception for embedding operations."""


class EmbeddingConfigError(EmbeddingError):
    """Raised when embedding provider configuration is missing or invalid."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when external embedding provider API fails or returns invalid data."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Contract for text embedding providers."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Compute 384-dimensional passage embeddings for document chunks."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Compute a 384-dimensional query embedding for search."""
        ...


class JinaEmbeddingProvider:
    """Production embedding provider targeting Jina AI's jina-embeddings-v3 API.

    Enforces:
    - Explicit Matryoshka output dimension of 384.
    - Separate tasks: 'retrieval.passage' for documents, 'retrieval.query' for queries.
    - Validation of vector dimensions and output counts.
    - Strict secret masking (never logs or leaks the API key).
    """

    API_URL = "https://api.jina.ai/v1/embeddings"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "jina-embeddings-v3",
        dimension: int = 384,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = model
        self.dimension = dimension
        self.timeout = timeout
        self._external_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._external_client is not None:
            return self._external_client
        return httpx.Client(timeout=self.timeout)

    def _call_api(self, texts: list[str], task: str) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingConfigError(
                "Jina API key is not configured. Set JINA_API_KEY in your environment."
            )

        if not texts:
            return []

        payload = {
            "model": self.model,
            "task": task,
            "dimensions": self.dimension,
            "input": texts,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        client = self._get_client()
        should_close = self._external_client is None

        try:
            response = client.post(self.API_URL, json=payload, headers=headers)
            if response.status_code != 200:
                sanitized_msg = response.text[:200]
                # Scrub any potential token mentions or explicit API key from provider error body
                if self.api_key:
                    sanitized_msg = sanitized_msg.replace(self.api_key, "[REDACTED]")
                sanitized_msg = re.sub(
                    r"(?:bearer|token|key)\s+[a-zA-Z0-9_\-]+",
                    "[REDACTED]",
                    sanitized_msg,
                    flags=re.I,
                )
                raise EmbeddingProviderError(
                    f"Jina API returned HTTP {response.status_code}: {sanitized_msg}"
                )

            data = response.json()
        except httpx.RequestError as exc:
            raise EmbeddingProviderError(
                f"Network communication failure connecting to Jina API: {type(exc).__name__}"
            ) from None
        except ValueError as exc:
            raise EmbeddingProviderError("Failed to parse JSON response from Jina API") from exc
        finally:
            if should_close:
                client.close()

        items = data.get("data")
        if not isinstance(items, list):
            raise EmbeddingProviderError("Malformed Jina response: 'data' list missing.")

        if len(items) != len(texts):
            raise EmbeddingProviderError(
                f"Count mismatch: expected {len(texts)} embeddings, received {len(items)}."
            )

        # Preserve input order using the returned 'index' attribute if present
        sorted_items = sorted(items, key=lambda it: it.get("index", 0))

        embeddings: list[list[float]] = []
        for idx, item in enumerate(sorted_items):
            vec = item.get("embedding")
            if not isinstance(vec, list):
                raise EmbeddingProviderError(f"Embedding at index {idx} is not a valid list.")
            if len(vec) != self.dimension:
                raise EmbeddingProviderError(
                    f"Dimension mismatch at index {idx}: expected {self.dimension}, got {len(vec)}."
                )
            embeddings.append(vec)

        return embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunk texts using passage task."""
        return self._call_api(texts, task="retrieval.passage")

    def embed_query(self, text: str) -> list[float]:
        """Embed a single user search query using query task."""
        clean_text = text.strip()
        if not clean_text:
            # Fallback for empty query to avoid provider error
            return [0.0] * self.dimension

        results = self._call_api([clean_text], task="retrieval.query")
        if not results:
            raise EmbeddingProviderError("Jina API returned no embeddings for query.")
        return results[0]


class DeterministicFakeEmbeddingProvider:
    """Deterministic, fast pseudo-embedding provider for isolated tests.

    Generates reproducible 384-dimensional unit vectors based on text token hashing.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _vectorize(self, text: str, prefix: str = "") -> list[float]:
        clean = text.strip().lower()
        if not clean:
            return [0.0] * self.dimension

        vector = [0.0] * self.dimension
        words = clean.split()
        for word_idx, word in enumerate(words):
            h = hashlib.sha256(f"{prefix}:{word}".encode()).digest()
            for i in range(min(len(h), self.dimension)):
                slot = (i * 13 + word_idx * 7) % self.dimension
                val = (h[i] - 128) / 128.0
                vector[slot] += val

        # Normalize to unit vector
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            return [v / norm for v in vector]
        return [1.0 / math.sqrt(self.dimension)] * self.dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(t, prefix="doc") for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vectorize(text, prefix="doc")
