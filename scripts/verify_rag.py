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
                "label": "EN Preparation & Fasting Query",
                "query": "What should I do if I accidentally eat while fasting?",
                "expected_outcome": "GOOD",
                "expected_document_titles": [
                    "Patient Test Preparation & Specimen Collection Guide"
                ],
                "expected_section": "Fasting and Hydration",
            },
            {
                "label": "AR Specimen Quality / Recollection Query",
                "query": "لو العينة اترفضت بسبب مشكلة في الجودة أعمل إيه؟",
                "expected_outcome": "GOOD",
                "expected_document_titles": [
                    "Specimen Acceptance, Recollection & Quality Exceptions Guide",
                    "Results Delivery, Turnaround & Report Access Guide",
                ],
                "expected_section": None,
            },
            {
                "label": "EN Privacy & Authorized Access Query",
                "query": "Can my wife access my lab report for me?",
                "expected_outcome": "GOOD",
                "expected_document_titles": [
                    "Patient Identification, Privacy & Authorized Access Guide",
                    "Results Delivery, Turnaround & Report Access Guide",
                ],
                "expected_section": None,
            },
            {
                "label": "AR Reschedule Home Visit Query",
                "query": "لو عايز أغير ميعاد الزيارة المنزلية أعمل إيه؟",
                "expected_outcome": "GOOD",
                "expected_document_titles": [
                    "Appointment Booking, Rescheduling & Cancellation Policy",
                    "Home Sample Collection Service Policy",
                ],
                "expected_section": None,
            },
            {
                "label": "EN Complaint & Duplicate Payment Query",
                "query": "How do I complain about a duplicate payment?",
                "expected_outcome": "GOOD",
                "expected_document_titles": [
                    "Customer Service, Complaints, Refunds & Escalation Policy",
                    "Appointment Booking, Rescheduling & Cancellation Policy",
                ],
                "expected_section": None,
            },
            {
                "label": "Unsupported / Non-Knowledge Query",
                "query": "Does MediLab provide MRI scans?",
                "expected_outcome": "NO_KNOWLEDGE",
                "expected_document_titles": [],
                "expected_section": None,
            },
        ]

        print("=" * 80)
        print("MediLab AI — Structure-Aware PDF Knowledge Corpus Retrieval Verification")
        print("=" * 80)
        print(f"Database Target:   {app.config.get('SQLALCHEMY_DATABASE_URI', '').split('@')[-1]}")
        print(f"Embedding Model:   {model} ({dimension} dim)")
        print("=" * 80)

        passed = 0
        for idx, tc in enumerate(test_cases, start=1):
            print(f"\n[Case {idx}/{len(test_cases)}] {tc['label']}")
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
                    meta = ch.source_metadata or {}
                    sec = meta.get("section_title") or "N/A"
                    page = meta.get("page_start") or "N/A"
                    src = meta.get("source_file") or "N/A"
                    print(
                        f"    #{rank} Chunk #{ch.chunk_id} | Doc #{ch.document_id} (v{ch.document_version}) "
                        f'"{ch.document_title}"\n'
                        f"       Section:     {sec}\n"
                        f"       Page:        p. {page}\n"
                        f"       Source File: {src}\n"
                        f"       RRF Score:   {ch.rrf_score:.5f} (SemRank={ch.semantic_rank}, LexRank={ch.lexical_rank})"
                    )
                    # Print brief content preview
                    preview = " ".join(ch.content.split()[:25])
                    print(f'       Preview:     "{preview}..."')
            else:
                print("  Retrieved Chunks: None (Correct deterministic no-answer)")

            # Strict verification of outcome, top source provenance, and zero-chunk guarantee
            case_passed = True
            if res.outcome != tc["expected_outcome"]:
                print(f"  STATUS: FAIL (Outcome {res.outcome} != {tc['expected_outcome']})")
                case_passed = False
            elif tc["expected_outcome"] == "NO_KNOWLEDGE":
                if len(res.final_chunks) != 0:
                    print(
                        f"  STATUS: FAIL (Expected 0 chunks for NO_KNOWLEDGE, got {len(res.final_chunks)})"
                    )
                    case_passed = False
            else:
                expected_titles = tc["expected_document_titles"]
                top_title = res.final_chunks[0].document_title if res.final_chunks else None
                if top_title not in expected_titles:
                    print(
                        f"  STATUS: FAIL (Top document '{top_title}' not in expected {expected_titles})"
                    )
                    case_passed = False
                elif tc.get("expected_section"):
                    top_meta = res.final_chunks[0].source_metadata or {}
                    top_section = top_meta.get("section_title", "")
                    if tc["expected_section"].lower() not in top_section.lower():
                        print(
                            f"  STATUS: WARNING/FAIL (Top section '{top_section}' does not match expected '{tc['expected_section']}')"
                        )
                        case_passed = False

            if case_passed:
                print("  STATUS: PASS")
                passed += 1

        print("\n" + "=" * 80)
        print(f"RAG Verification Complete: {passed}/{len(test_cases)} Passed.")
        print("=" * 80)
        return 0 if passed == len(test_cases) else 1


if __name__ == "__main__":
    sys.exit(main())
