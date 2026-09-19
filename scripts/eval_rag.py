"""Evaluation runner for Phase 2 hybrid RAG retrieval benchmark.

Calculates:
- Calibration vs post-calibration validation metrics
- Recall@4
- MRR (Mean Reciprocal Rank) across known-answer cases
- No-answer correctness
- Retry rate
- Latency statistics (Average, Median P50, P95, Min, Max)
- Dynamic threshold evaluation with honest status reporting

The post-calibration validation cases are NOT described as an independent holdout because
some were probed during QA hardening. Correctness target failures return a non-zero exit
code; latency remains an observed, non-blocking internal optimization target.

Usage:
    uv run python scripts/eval_rag.py
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from app import create_app
from app.rag.embeddings import get_embedding_provider
from app.rag.service import RAGService


def get_git_commit() -> str:
    """Return the current repository commit for evaluation provenance."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()[:12]
    except Exception:
        return "unknown"


def compute_percentile(data: list[float], p: float) -> float:
    """Compute an interpolated percentile value from a float series."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


def evaluate_split(
    cases: list[dict],
    rag: RAGService,
) -> tuple[dict, list[dict]]:
    """Evaluate one labeled split and return aggregate stats plus per-case evidence."""
    hits_at_4 = 0
    reciprocal_ranks: list[float] = []
    no_answer_correct = 0
    total_no_answer_cases = 0
    section_cases = 0
    section_hits = 0
    retries = 0
    latencies: list[float] = []
    embed_times: list[float] = []
    sem_times: list[float] = []
    lex_times: list[float] = []
    case_results: list[dict] = []

    for tc in cases:
        query = tc["query"]
        expected_titles = tc["expected_document_titles"]
        expected_section = tc.get("expected_section")
        is_no_answer = tc["expected_no_answer"]
        split_name = tc.get("split", "calibration")

        result = rag.retrieve(query)
        latencies.append(result.latency_ms)
        embed_times.append(result.diagnostics.embed_ms)
        sem_times.append(result.diagnostics.semantic_ms)
        lex_times.append(result.diagnostics.lexical_ms)
        if result.diagnostics.retry_used:
            retries += 1

        retrieved_titles = [chunk.document_title for chunk in result.final_chunks]
        first_hit_rank = 0

        if is_no_answer:
            total_no_answer_cases += 1
            is_correct = result.outcome == "NO_KNOWLEDGE" and len(result.final_chunks) == 0
            if is_correct:
                no_answer_correct += 1
        else:
            for rank, title in enumerate(retrieved_titles[:4], start=1):
                if title in expected_titles:
                    first_hit_rank = rank
                    break

            reciprocal_ranks.append(1.0 / first_hit_rank if first_hit_rank else 0.0)
            if first_hit_rank:
                hits_at_4 += 1

            if expected_section:
                section_cases += 1
                sec_match = False
                for ch in result.final_chunks[:4]:
                    meta = ch.source_metadata or {}
                    sec_title = meta.get("section_title") or ""
                    if expected_section.lower() in sec_title.lower():
                        sec_match = True
                        break
                if sec_match:
                    section_hits += 1

        case_results.append(
            {
                "id": tc["id"],
                "split": split_name,
                "query": query,
                "language": tc["language"],
                "outcome": result.outcome,
                "expected_no_answer": is_no_answer,
                "first_rank": first_hit_rank
                if not is_no_answer
                else (
                    "N/A (Correct)"
                    if result.outcome == "NO_KNOWLEDGE" and len(result.final_chunks) == 0
                    else "False Positive"
                ),
                "latency_ms": round(result.latency_ms, 1),
                "retrieved": retrieved_titles,
            }
        )

    known_cases = len(cases) - total_no_answer_cases
    recall_at_4 = hits_at_4 / known_cases if known_cases else 0.0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0
    no_answer_accuracy = no_answer_correct / total_no_answer_cases if total_no_answer_cases else 0.0
    section_accuracy = section_hits / section_cases if section_cases else 1.0
    retry_rate = retries / len(cases) if cases else 0.0

    stats = {
        "total_cases": len(cases),
        "known_cases": known_cases,
        "no_answer_cases": total_no_answer_cases,
        "hits_at_4": hits_at_4,
        "recall_at_4": recall_at_4,
        "mrr": mrr,
        "no_answer_correct": no_answer_correct,
        "no_answer_accuracy": no_answer_accuracy,
        "section_cases": section_cases,
        "section_hits": section_hits,
        "section_accuracy": section_accuracy,
        "retries": retries,
        "retry_rate": retry_rate,
        "avg_latency": sum(latencies) / len(latencies) if latencies else 0.0,
        "p50_latency": compute_percentile(latencies, 50),
        "p95_latency": compute_percentile(latencies, 95),
        "min_latency": min(latencies) if latencies else 0.0,
        "max_latency": max(latencies) if latencies else 0.0,
        "avg_embed": sum(embed_times) / len(embed_times) if embed_times else 0.0,
        "avg_sem": sum(sem_times) / len(sem_times) if sem_times else 0.0,
        "avg_lex": sum(lex_times) / len(lex_times) if lex_times else 0.0,
    }
    return stats, case_results


def main() -> int:
    eval_file = Path(__file__).resolve().parent.parent / "evals" / "rag_cases.json"
    if not eval_file.exists():
        print(f"ERROR: Evaluation cases file not found at {eval_file}")
        return 1

    with open(eval_file, encoding="utf-8") as file_handle:
        cases = json.load(file_handle)

    calibration_cases = [case for case in cases if case.get("split") == "calibration"]
    validation_cases = [
        case for case in cases if case.get("split") == "post_calibration_validation"
    ]

    if not calibration_cases or not validation_cases:
        print("ERROR: Evaluation dataset must include calibration and validation cases.")
        return 1

    app = create_app()
    with app.app_context():
        provider = get_embedding_provider(app.config)
        rag = RAGService(embedding_provider=provider)
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        db_masked = db_uri.split("@")[-1] if "@" in db_uri else "database"
        model = app.config.get("EMBEDDING_MODEL", "jina-embeddings-v3")
        dimension = app.config.get("EMBEDDING_DIMENSION", 384)

        print("=" * 75)
        print(
            f"MediLab AI — RAG Evaluation Runner ({len(cases)} cases: "
            f"{len(calibration_cases)} calibration, "
            f"{len(validation_cases)} post-calibration validation)"
        )
        print("=" * 75)

        cal_stats, cal_results = evaluate_split(calibration_cases, rag)
        val_stats, val_results = evaluate_split(validation_cases, rag)
        all_results = cal_results + val_results

        combined_latencies = [case["latency_ms"] for case in all_results]
        combined_known = cal_stats["known_cases"] + val_stats["known_cases"]
        combined_hits = cal_stats["hits_at_4"] + val_stats["hits_at_4"]
        combined_recall = combined_hits / combined_known if combined_known else 0.0
        combined_no_answer_total = cal_stats["no_answer_cases"] + val_stats["no_answer_cases"]
        combined_no_answer_correct = cal_stats["no_answer_correct"] + val_stats["no_answer_correct"]
        combined_no_answer_accuracy = (
            combined_no_answer_correct / combined_no_answer_total
            if combined_no_answer_total
            else 0.0
        )
        combined_retries = cal_stats["retries"] + val_stats["retries"]
        combined_retry_rate = combined_retries / len(cases) if cases else 0.0
        combined_mrr = (
            (
                cal_stats["mrr"] * cal_stats["known_cases"]
                + val_stats["mrr"] * val_stats["known_cases"]
            )
            / combined_known
            if combined_known
            else 0.0
        )
        combined_section_cases = cal_stats["section_cases"] + val_stats["section_cases"]
        combined_section_hits = cal_stats["section_hits"] + val_stats["section_hits"]
        combined_section_accuracy = (
            combined_section_hits / combined_section_cases if combined_section_cases else 1.0
        )

        combined_stats = {
            "recall_at_4": combined_recall,
            "hits_at_4": combined_hits,
            "known_cases": combined_known,
            "mrr": combined_mrr,
            "no_answer_accuracy": combined_no_answer_accuracy,
            "no_answer_correct": combined_no_answer_correct,
            "no_answer_cases": combined_no_answer_total,
            "section_accuracy": combined_section_accuracy,
            "section_hits": combined_section_hits,
            "section_cases": combined_section_cases,
            "retry_rate": combined_retry_rate,
            "retries": combined_retries,
            "total_cases": len(cases),
            "avg_latency": (
                sum(combined_latencies) / len(combined_latencies) if combined_latencies else 0.0
            ),
            "p50_latency": compute_percentile(combined_latencies, 50),
            "p95_latency": compute_percentile(combined_latencies, 95),
            "min_latency": min(combined_latencies) if combined_latencies else 0.0,
            "max_latency": max(combined_latencies) if combined_latencies else 0.0,
        }

        recall_status = "PASS" if combined_stats["recall_at_4"] >= 0.90 else "FAIL"
        mrr_status = "PASS" if combined_stats["mrr"] >= 0.85 else "FAIL"
        no_answer_status = "PASS" if combined_stats["no_answer_accuracy"] >= 1.0 else "FAIL"
        retry_status = "PASS" if combined_stats["retry_rate"] <= 0.20 else "FAIL"
        latency_status = (
            "PASS"
            if combined_stats["p95_latency"] < 500.0
            else "TARGET MISSED / NEEDS OPTIMIZATION"
        )
        correctness_passed = all(
            status == "PASS" for status in (recall_status, mrr_status, no_answer_status)
        )

        print("-" * 75)
        print(f"[Calibration Set] ({len(calibration_cases)} cases):")
        print(f"  Recall@4:              {cal_stats['recall_at_4'] * 100:.1f}%")
        print(f"  MRR:                   {cal_stats['mrr']:.4f}")
        print(f"  No-Answer Accuracy:    {cal_stats['no_answer_accuracy'] * 100:.1f}%")
        print(f"  Section Recall@4:{cal_stats['section_accuracy'] * 100:.1f}%")
        print(f"[Post-Calibration Validation] ({len(validation_cases)} cases):")
        print(f"  Recall@4:              {val_stats['recall_at_4'] * 100:.1f}%")
        print(f"  MRR:                   {val_stats['mrr']:.4f}")
        print(f"  No-Answer Accuracy:    {val_stats['no_answer_accuracy'] * 100:.1f}%")
        print(f"  Section Recall@4:{val_stats['section_accuracy'] * 100:.1f}%")
        print("-" * 75)
        print(f"[Combined Overall] ({len(cases)} cases):")
        print(
            f"  Recall@4:              {combined_stats['recall_at_4'] * 100:.1f}% "
            f"({combined_stats['hits_at_4']}/{combined_stats['known_cases']}) -> "
            f"[{recall_status}]"
        )
        print(f"  MRR:                   {combined_stats['mrr']:.4f} -> [{mrr_status}]")
        print(
            f"  No-Answer Accuracy:    {combined_stats['no_answer_accuracy'] * 100:.1f}% "
            f"({combined_stats['no_answer_correct']}/{combined_stats['no_answer_cases']}) -> "
            f"[{no_answer_status}]"
        )
        print(
            f"  Section Recall@4:{combined_stats['section_accuracy'] * 100:.1f}% "
            f"({combined_stats['section_hits']}/{combined_stats['section_cases']}) -> "
            f"[Measured]"
        )
        print(
            f"  Retry Rate:            {combined_stats['retry_rate'] * 100:.1f}% "
            f"({combined_stats['retries']}/{combined_stats['total_cases']}) -> "
            f"[{retry_status}]"
        )
        print(f"  Latency Average:       {combined_stats['avg_latency']:.1f}ms")
        print(f"  Latency Median (P50):  {combined_stats['p50_latency']:.1f}ms")
        print(
            f"  Latency P95:           {combined_stats['p95_latency']:.1f}ms "
            f"(Target: <500ms) -> [{latency_status}]"
        )
        print(
            f"  Latency Min / Max:     {combined_stats['min_latency']:.1f}ms / "
            f"{combined_stats['max_latency']:.1f}ms"
        )
        print("=" * 75)

        report_dir = Path(__file__).resolve().parent.parent / "docs" / "evaluation"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "phase2_rag_eval.md"
        commit_sha = get_git_commit()
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        table_rows = []
        for case in all_results:
            table_rows.append(
                f"| {case['id']} | {case['split']} | {case['language'].upper()} | "
                f"{case['query'][:42]}... | {case['outcome']} | {case['first_rank']} | "
                f"{case['latency_ms']}ms |"
            )
        table_content = "\n".join(table_rows)

        report_content = f"""# MediLab AI — Phase 2 Hybrid RAG Evaluation Report

## Metadata
- **Date / Time:** {now_str}
- **Git Commit SHA:** `{commit_sha}`
- **Database Endpoint:** `{db_masked}`
- **Embedding Provider:** Jina AI
- **Embedding Model:** `{model}`
- **Vector Dimension:** `{dimension}`
- **Evaluation Cases:** {len(cases)} cases ({len(calibration_cases)} calibration, {len(validation_cases)} post-calibration validation)

> The validation split is intentionally not called an independent holdout. Some of these
> cases were inspected during QA hardening, so these metrics are validation evidence rather
> than an unbiased generalization estimate.

---

## Executive Summary Metrics

| Split | Cases | Recall@4 | MRR | No-Answer Accuracy | Section Recall@4 | Retry Rate | Avg Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Calibration Set** | {len(calibration_cases)} | **{cal_stats["recall_at_4"] * 100:.1f}%** ({cal_stats["hits_at_4"]}/{cal_stats["known_cases"]}) | **{cal_stats["mrr"]:.4f}** | **{cal_stats["no_answer_accuracy"] * 100:.1f}%** | {cal_stats["section_accuracy"] * 100:.1f}% | {cal_stats["retry_rate"] * 100:.1f}% | {cal_stats["avg_latency"]:.1f}ms |
| **Post-Calibration Validation** | {len(validation_cases)} | **{val_stats["recall_at_4"] * 100:.1f}%** ({val_stats["hits_at_4"]}/{val_stats["known_cases"]}) | **{val_stats["mrr"]:.4f}** | **{val_stats["no_answer_accuracy"] * 100:.1f}%** | {val_stats["section_accuracy"] * 100:.1f}% | {val_stats["retry_rate"] * 100:.1f}% | {val_stats["avg_latency"]:.1f}ms |
| **Combined Overall** | {len(cases)} | **{combined_stats["recall_at_4"] * 100:.1f}%** ({combined_stats["hits_at_4"]}/{combined_stats["known_cases"]}) | **{combined_stats["mrr"]:.4f}** | **{combined_stats["no_answer_accuracy"] * 100:.1f}%** | {combined_stats["section_accuracy"] * 100:.1f}% | {combined_stats["retry_rate"] * 100:.1f}% | {combined_stats["avg_latency"]:.1f}ms |

## Benchmark Target Evaluation

| Metric | Measured Value | Benchmark Target | Status |
| :--- | :--- | :--- | :--- |
| **Recall@4** | **{combined_stats["recall_at_4"] * 100:.1f}%** ({combined_stats["hits_at_4"]}/{combined_stats["known_cases"]}) | >= 90.0% | **{recall_status}** |
| **MRR** | **{combined_stats["mrr"]:.4f}** | >= 0.8500 | **{mrr_status}** |
| **No-Answer Accuracy** | **{combined_stats["no_answer_accuracy"] * 100:.1f}%** ({combined_stats["no_answer_correct"]}/{combined_stats["no_answer_cases"]}) | 100.0% | **{no_answer_status}** |
| **Section Recall@4** | **{combined_stats["section_accuracy"] * 100:.1f}%** ({combined_stats["section_hits"]}/{combined_stats["section_cases"]}) | Informational / Observable | **Measured ({combined_stats["section_hits"]}/{combined_stats["section_cases"]})** |
| **Retry Rate** | **{combined_stats["retry_rate"] * 100:.1f}%** ({combined_stats["retries"]}/{combined_stats["total_cases"]}) | <= 20.0% | **{retry_status}** |
| **P95 Latency (Internal Target)** | **{combined_stats["p95_latency"]:.1f}ms** | < 500.0ms | **{latency_status}** |
| **Median (P50) Latency** | **{combined_stats["p50_latency"]:.1f}ms** | Informational | Informational |
| **Average Total Latency** | **{combined_stats["avg_latency"]:.1f}ms** | Informational | Informational |
| **Min / Max Latency** | **{combined_stats["min_latency"]:.1f}ms / {combined_stats["max_latency"]:.1f}ms** | Range | Informational |

---

## Detailed Evaluation Cases

| Case ID | Split | Lang | Query Preview | Outcome | Hit Rank | Total Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{table_content}

---

## Evidence Notes
1. Correctness target failures make this script exit non-zero.
2. The latency target is engineering-only and non-blocking; misses are reported honestly.
3. The post-calibration validation set is not an independent holdout because QA diagnostics inspected some cases.
4. Unsupported services must remain `NO_KNOWLEDGE` with zero final chunks.
"""
        with open(report_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(report_content)

        print(f"Report written to: {report_path}")
        if not correctness_passed:
            print("ERROR: One or more correctness acceptance targets failed.")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
