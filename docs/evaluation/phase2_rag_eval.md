# MediLab AI — Phase 2 Hybrid RAG Evaluation Report

## Metadata
- **Evaluation Date / Time:** 2026-09-17 15:29:26 UTC
- **Evaluation Run Code SHA:** `8c73c4f843c1`
- **Current Retrieval Code Head After QA Round 2 Hardening:** `cdf8d83aa163b00a7e3bec84ab1d846ee6f308e3`
- **Database Endpoint:** `aws-1-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require`
- **Embedding Provider:** Jina AI
- **Embedding Model:** `jina-embeddings-v3`
- **Vector Dimension:** `384`
- **Evaluation Cases:** 20 cases (15 calibration, 5 post-calibration validation)

> **Evidence scope:** the measured values below come from the live evaluation run recorded at code SHA `8c73c4f843c1`. Subsequent QA Round 2 commits hardened dependency injection, context budgeting, evaluation accounting, and stale-version retrieval guards. The five validation cases are intentionally **not** described as an independent holdout because some were inspected during QA hardening.

---

## Executive Summary Metrics

| Split | Cases | Recall@4 | MRR | No-Answer Accuracy | Retry Rate | Avg Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Calibration Set** | 15 | **100.0%** (12/12) | **1.0000** | **100.0%** (3/3) | 13.3% | 2882.1ms |
| **Post-Calibration Validation** | 5 | **100.0%** (4/4) | **1.0000** | **100.0%** (1/1) | 20.0% | 2032.5ms |
| **Combined Overall** | 20 | **100.0%** (16/16) | **1.0000** | **100.0%** (4/4) | 15.0% | 2669.7ms |

## Benchmark Target Evaluation

| Metric | Measured Value | Benchmark Target | Status |
| :--- | :--- | :--- | :--- |
| **Recall@4** | **100.0%** (16/16) | >= 90.0% | **PASS** |
| **MRR** | **1.0000** | >= 0.8500 | **PASS** |
| **No-Answer Accuracy** | **100.0%** (4/4) | 100.0% | **PASS** |
| **Retry Rate** | **15.0%** (3/20) | <= 20.0% | **PASS** |
| **P95 Latency (Internal Target)** | **5098.9ms** | < 500.0ms | **TARGET MISSED / NEEDS OPTIMIZATION** |
| **Median (P50) Latency** | **2853.4ms** | Informational | Informational |
| **Average Total Latency** | **2669.7ms** | Informational | Informational |
| **Min / Max Latency** | **944.9ms / 5118.2ms** | Range | Informational |

---

## Detailed Evaluation Cases

| Case ID | Split | Lang | Query Preview | Outcome | Hit Rank | Total Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| RAG-01 | calibration | EN | What are the fasting guidelines for a lipi... | GOOD | 1 | 5118.2ms |
| RAG-02 | calibration | EN | How many hours do I need to fast before fa... | GOOD | 1 | 3358.9ms |
| RAG-03 | calibration | AR | هل يمكن شرب الماء أثناء فترة الصيام للتحال... | GOOD | 1 | 2895.3ms |
| RAG-04 | calibration | AR | هل لازم أصوم قبل تحليل الدهون الكامل؟... | GOOD | 1 | 3018.7ms |
| RAG-05 | calibration | EN | What is the cancellation policy for home c... | GOOD | 1 | 3802.6ms |
| RAG-06 | calibration | EN | How much notice is required to reschedule ... | GOOD | 1 | 5097.9ms |
| RAG-07 | calibration | AR | هل في غرامة لو لغيت موعد الزيارة المنزلية ... | GOOD | 1 | 3545.2ms |
| RAG-08 | calibration | EN | Which areas in Cairo are covered by MediLa... | GOOD | 1 | 2811.6ms |
| RAG-09 | calibration | EN | Can someone come to my home in Maadi to dr... | GOOD | 1 | 1391.5ms |
| RAG-10 | calibration | AR | خدمة سحب العينات من المنزل بتغطي مدينة نصر... | GOOD | 1 | 944.9ms |
| RAG-11 | calibration | EN | How long does it take to receive Vitamin D... | GOOD | 1 | 1919.9ms |
| RAG-12 | calibration | AR | نتيجة تحليل الغدة الدرقية بتطلع بعد كام يو... | GOOD | 1 | 1650.7ms |
| RAG-13 | calibration | EN | Does MediLab provide MRI and CT scan imagi... | NO_KNOWLEDGE | N/A (Correct) | 1243.8ms |
| RAG-14 | calibration | AR | هل المعمل بيعمل عمليات جراحية أو مناظير با... | NO_KNOWLEDGE | N/A (Correct) | 2929.6ms |
| RAG-15 | calibration | EN | Can I get a prescription refill for antibi... | NO_KNOWLEDGE | N/A (Correct) | 3502.9ms |
| RAG-16 | post_calibration_validation | EN | How many hours before an in-clinic appoint... | GOOD | 1 | 1745.2ms |
| RAG-17 | post_calibration_validation | AR | هل خدمة الزيارة المنزلية لسحب العينات متوف... | GOOD | 1 | 3196.3ms |
| RAG-18 | post_calibration_validation | EN | When are standard CBC blood test results d... | GOOD | 1 | 1783.6ms |
| RAG-19 | post_calibration_validation | AR | هل مسموح بشرب القهوة أو الشاي قبل تحليل ال... | GOOD | 1 | 987.7ms |
| RAG-20 | post_calibration_validation | EN | Can MediLab administer chemotherapy infusi... | NO_KNOWLEDGE | N/A (Correct) | 2449.6ms |

---

## Evidence Notes
1. **Calibration vs validation:** the 15 calibration cases were used during threshold tuning. The five later cases are post-calibration validation evidence, not an unbiased independent holdout.
2. **Deterministic no-answer:** unsupported services in the evaluated set returned `NO_KNOWLEDGE` with zero final chunks.
3. **Latency:** the internal hybrid retrieval P95 target of <500ms was missed in this WAN/cloud measurement. This is reported as an optimization item rather than hidden or converted into a false PASS.
4. **Current evaluator behavior:** the QA-hardened `scripts/eval_rag.py` computes MRR over known-answer cases, returns non-zero on correctness-target failure, and keeps the latency target non-blocking.
5. **Current retrieval hardening:** QA Round 2 added stale chunk/document-version rejection so READY documents cannot return chunks whose `document_version` metadata does not match the current document version.
