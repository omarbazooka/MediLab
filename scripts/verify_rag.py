"""Interactive RAG verification script running benchmark queries against indexed knowledge.

Tests:
1. English known query: "What is the cancellation policy for a home visit?"
2. Arabic known query: "هل لازم أصوم قبل تحليل الدهون؟"
3. English paraphrase: "Can someone come to my house to collect the sample?"
4. Non-knowledge query: "Does MediLab provide MRI scans?"

Usage:
    uv run python scripts/verify_rag.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from app import create_app
from app.rag.embeddings import JinaEmbeddingProvider
from app.rag.service import RAGService


def main() -> int:
    app = create_app()
    with app.app_context():
        api_key = app.config.get("JINA_API_KEY", "")
        model = app.config.get("EMBEDDING_MODEL", "jina-embeddings-v3")
        dimension = app.config.get("EMBEDDING_DIMENSION", 384)

        provider = JinaEmbeddingProvider(
            api_key=api_key,
            model=model,
            dimension=dimension,
        )
        rag = RAGService(embedding_provider=provider)

        test_cases = [
            {
                "label": "English Known-Answer Policy Query",
                "query": "What is the cancellation policy for a home visit?",
                "expected_outcome": "GOOD",
            },
            {
                "label": "Arabic Known-Answer Preparation Query",
                "query": "هل لازم أصوم قبل تحليل الدهون؟",
                "expected_outcome": "GOOD",
            },
            {
                "label": "English Paraphrased Service Query",
                "query": "Can someone come to my house to collect the sample?",
                "expected_outcome": "GOOD",
            },
            {
                "label": "Unsupported / Non-Knowledge Query",
                "query": "Does MediLab provide MRI scans?",
                "expected_outcome": "NO_KNOWLEDGE",
            },
        ]

        print("=" * 80)
        print("MediLab AI — Standalone Hybrid RAG Retrieval Live Verification")
        print("=" * 80)
        print(f"Database Target:   {app.config.get('SQLALCHEMY_DATABASE_URI', '').split('@')[-1]}")
        print(f"Embedding Model:   {model} ({dimension} dim)")
        print("=" * 80)

        passed = 0
        for idx, tc in enumerate(test_cases, start=1):
            print(f"\n[Case {idx}/4] {tc['label']}")
            print(f'  Input Query:     "{tc["query"]}"')

            try:
                res = rag.retrieve(tc["query"])
            except Exception as exc:
                print(f"  FAILED with exception: {exc}")
                return 1

            print(f'  Rewritten Query: "{res.rewritten_query}"')
            print(f"  Outcome:         {res.outcome} (Expected: {tc['expected_outcome']})")
            print(
                f"  Attempts:        {res.attempt_count} (Retry used: {res.diagnostics.retry_used})"
            )
            print(f"  Degraded Mode:   {res.degraded_mode}")
            print(
                f"  Latency Total:   {res.latency_ms:.1f}ms "
                f"[Embed: {res.diagnostics.embed_ms:.1f}ms, "
                f"Sem: {res.diagnostics.semantic_ms:.1f}ms, "
                f"Lex: {res.diagnostics.lexical_ms:.1f}ms, "
                f"Fuse: {res.diagnostics.fusion_ms:.1f}ms]"
            )

            if res.final_chunks:
                print(f"  Retrieved Chunks ({len(res.final_chunks)} passages):")
                for rank, ch in enumerate(res.final_chunks, start=1):
                    print(
                        f"    #{rank} Doc #{ch.document_id} (v{ch.document_version} #{ch.chunk_index}) "
                        f'"{ch.document_title}" | RRF={ch.rrf_score:.5f} '
                        f"(SemRank={ch.semantic_rank}, LexRank={ch.lexical_rank}, Dist={ch.cosine_distance})"
                    )
                    # Print brief content preview
                    preview = " ".join(ch.content.split()[:20])
                    print(f'       Preview: "{preview}..."')
            else:
                print("  Retrieved Chunks: None (Correct deterministic no-answer)")

            # Verify expectations
            if res.outcome == tc["expected_outcome"]:
                print("  STATUS: PASS")
                passed += 1
            else:
                print(f"  STATUS: FAIL (Outcome {res.outcome} != {tc['expected_outcome']})")

        print("\n" + "=" * 80)
        print(f"RAG Verification Complete: {passed}/{len(test_cases)} Passed.")
        print("=" * 80)
        return 0 if passed == len(test_cases) else 1


if __name__ == "__main__":
    sys.exit(main())
