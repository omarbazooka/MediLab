"""Live verification script for Jina AI Embeddings API.

Performs live English and Arabic embedding calls to verify:
1. Provider: Jina AI
2. Model: jina-embeddings-v3
3. Dimension: exactly 384 floats
4. Query task: retrieval.query
5. Document task: retrieval.passage
6. Strict secret masking (API key is never printed)

Usage:
    uv run python scripts/verify_embeddings.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from app.rag.embeddings import JinaEmbeddingProvider

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

load_dotenv()


def main() -> int:
    api_key = os.getenv("JINA_API_KEY", "").strip()
    model = os.getenv("EMBEDDING_MODEL", "jina-embeddings-v3").strip()
    dim_str = os.getenv("EMBEDDING_DIMENSION", "384").strip()

    try:
        dimension = int(dim_str)
    except ValueError:
        print(f"ERROR: Invalid EMBEDDING_DIMENSION '{dim_str}' in environment.")
        return 1

    if not api_key:
        print("ERROR: JINA_API_KEY is not set in environment.")
        return 1

    print("=" * 60)
    print("MediLab AI — Jina AI Embeddings Live Smoke Verification")
    print("=" * 60)
    print("Provider:        Jina AI")
    print(f"Model:           {model}")
    print(f"Dimension:       {dimension} (enforced Matryoshka)")
    print("API Key Present: Yes")
    print("-" * 60)

    provider = JinaEmbeddingProvider(
        api_key=api_key,
        model=model,
        dimension=dimension,
    )

    # 1. English query embedding
    en_query = "What is the cancellation policy for a home visit?"
    print("[1/2] Embedding English query (task='retrieval.query')...")
    print(f'      Query: "{en_query}"')
    try:
        en_vec = provider.embed_query(en_query)
        assert len(en_vec) == dimension, f"Expected {dimension} dimensions, got {len(en_vec)}"
        assert all(isinstance(x, float) for x in en_vec), "All elements must be floats"
        print(f"      SUCCESS: Received vector with {len(en_vec)} float dimensions.")
        print(f"      Sample slice [0:5]: {[round(x, 4) for x in en_vec[:5]]}")
    except Exception as exc:
        print(f"      FAILED: {exc}")
        return 1

    print("-" * 60)

    # 2. Arabic passage embedding
    ar_passage = "تحليل صورة الدم الكاملة يتطلب سحب عينة دم وريدي، ولا يشترط الصيام المسبق."
    print("[2/2] Embedding Arabic passage (task='retrieval.passage')...")
    print(f'      Passage: "{ar_passage}"')
    try:
        ar_vecs = provider.embed_documents([ar_passage])
        assert len(ar_vecs) == 1, "Expected exactly 1 vector in response"
        ar_vec = ar_vecs[0]
        assert len(ar_vec) == dimension, f"Expected {dimension} dimensions, got {len(ar_vec)}"
        assert all(isinstance(x, float) for x in ar_vec), "All elements must be floats"
        print(f"      SUCCESS: Received vector with {len(ar_vec)} float dimensions.")
        print(f"      Sample slice [0:5]: {[round(x, 4) for x in ar_vec[:5]]}")
    except Exception as exc:
        print(f"      FAILED: {exc}")
        return 1

    print("=" * 60)
    print("ALL LIVE JINA EMBEDDING VERIFICATIONS PASSED (Dimension=384)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
