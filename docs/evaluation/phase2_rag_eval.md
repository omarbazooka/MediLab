# MediLab AI — Phase 2 Hybrid RAG Evaluation Report

## Metadata
- **Date / Time:** 2026-09-18 02:30:03 UTC
- **Git HEAD at execution:** `e9fc02b1cfd7`
- **Database Endpoint:** `aws-1-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require`
- **Embedding Provider:** Jina AI
- **Embedding Model:** `jina-embeddings-v3`
- **Vector Dimension:** `384`
- **Evaluation Cases:** 28 cases (19 calibration, 9 post-calibration validation)

> The validation split is intentionally not called an independent holdout. Some of these
> cases were inspected during QA hardening, so these metrics are validation evidence rather
> than an unbiased generalization estimate.

> **Provenance note:** This evaluation was executed while the PDF-ingestion changes were still
> uncommitted on top of the recorded Git HEAD. Those working-tree changes were subsequently
> committed as `a5d324a2d3b488426c5047fc55561385e499151c`. The metrics below are valid historical
> runtime evidence for that working tree, but they are not current-head evidence after later QA
> hardening. Re-run the evaluation before final Phase 2 signoff.

---

## Executive Summary Metrics

| Split | Cases | Recall@4 | MRR | No-Answer Accuracy | Section Recall@4 | Retry Rate | Avg Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Calibration Set** | 19 | **100.0%** (16/16) | **0.9375** | **100.0%** | 72.7% | 10.5% | 4758.9ms |
| **Post-Calibration Validation** | 9 | **100.0%** (7/7) | **1.0000** | **100.0%** | 75.0% | 11.1% | 2791.7ms |
| **Combined Overall** | 28 | **100.0%** (23/23) | **0.9565** | **100.0%** | 73.3% | 10.7% | 4126.6ms |

## Benchmark Target Evaluation

| Metric | Measured Value | Benchmark Target | Status |
| :--- | :--- | :--- | :--- |
| **Recall@4** | **100.0%** (23/23) | >= 90.0% | **PASS** |
| **MRR** | **0.9565** | >= 0.8500 | **PASS** |
| **No-Answer Accuracy** | **100.0%** (5/5) | 100.0% | **PASS** |
| **Section Recall@4** | **73.3%** (11/15) | Informational / Observable | **Measured (11/15)** |
| **Retry Rate** | **10.7%** (3/28) | <= 20.0% | **PASS** |
| **P95 Latency (Internal Target)** | **11262.1ms** | < 500.0ms | **TARGET MISSED / NEEDS OPTIMIZATION** |
| **Median (P50) Latency** | **2451.4ms** | Informational | Informational |
| **Average Total Latency** | **4126.6ms** | Informational | Informational |
| **Min / Max Latency** | **1138.5ms / 17011.1ms** | Range | Informational |

---

## Detailed Evaluation Cases

| Case ID | Split | Lang | Query Preview | Outcome | Hit Rank | Total Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| RAG-01 | calibration | EN | What are the fasting guidelines for a lipi... | GOOD | 1 | 10540.5ms |
| RAG-02 | calibration | EN | How many hours do I need to fast before fa... | GOOD | 1 | 7237.5ms |
| RAG-03 | calibration | AR | هل يمكن شرب الماء أثناء فترة الصيام للتحال... | GOOD | 1 | 7499.7ms |
| RAG-04 | calibration | AR | هل لازم أصوم قبل تحليل الدهون الكامل؟... | WEAK_RETRY | 1 | 17011.1ms |
| RAG-05 | calibration | EN | What is the cancellation policy for home c... | GOOD | 1 | 11650.6ms |
| RAG-06 | calibration | EN | How much notice is required to reschedule ... | GOOD | 2 | 7404.9ms |
| RAG-07 | calibration | AR | هل في غرامة لو لغيت موعد الزيارة المنزلية ... | GOOD | 1 | 1757.7ms |
| RAG-08 | calibration | EN | Which areas in Cairo are covered by MediLa... | GOOD | 1 | 2164.3ms |
| RAG-09 | calibration | EN | Can someone come to my home in Maadi to dr... | GOOD | 1 | 5919.9ms |
| RAG-10 | calibration | AR | خدمة سحب العينات من المنزل بتغطي مدينة نصر... | GOOD | 1 | 1425.0ms |
| RAG-11 | calibration | EN | How long does standard routine blood test ... | GOOD | 1 | 1477.7ms |
| RAG-12 | calibration | AR | نتيجة تحليل الغدة الدرقية بتطلع بعد كام يو... | WEAK_RETRY | 1 | 2867.7ms |
| RAG-13 | calibration | EN | Does MediLab provide MRI and CT scan imagi... | NO_KNOWLEDGE | N/A (Correct) | 2323.1ms |
| RAG-14 | calibration | AR | هل المعمل بيعمل عمليات جراحية أو مناظير با... | NO_KNOWLEDGE | N/A (Correct) | 1138.5ms |
| RAG-15 | calibration | EN | Can I get a prescription refill for antibi... | NO_KNOWLEDGE | N/A (Correct) | 2579.8ms |
| RAG-16 | calibration | EN | What happens if a blood specimen arrives c... | GOOD | 2 | 2041.2ms |
| RAG-17 | calibration | AR | لو العينة اترفضت بسبب مشكلة في الجودة أعمل... | GOOD | 1 | 1628.3ms |
| RAG-18 | calibration | EN | Can my spouse access my lab report for me?... | GOOD | 1 | 1915.6ms |
| RAG-19 | calibration | EN | How do I request a refund for an accidenta... | GOOD | 1 | 1836.8ms |
| RAG-20 | post_calibration_validation | EN | How many hours before an in-clinic appoint... | GOOD | 1 | 1898.2ms |
| RAG-21 | post_calibration_validation | AR | هل خدمة الزيارة المنزلية لسحب العينات متوف... | GOOD | 1 | 1673.6ms |
| RAG-22 | post_calibration_validation | EN | When are standard routine diagnostic blood... | GOOD | 1 | 2063.7ms |
| RAG-23 | post_calibration_validation | AR | هل مسموح بشرب القهوة أو الشاي قبل تحليل ال... | WEAK_RETRY | 1 | 3114.8ms |
| RAG-24 | post_calibration_validation | EN | Can MediLab administer chemotherapy infusi... | NO_KNOWLEDGE | N/A (Correct) | 1909.8ms |
| RAG-25 | post_calibration_validation | EN | How does specimen recollection affect the ... | GOOD | 1 | 4358.4ms |
| RAG-26 | post_calibration_validation | AR | هل يحق لأحد أقاربي استلام تقرير التحليل بد... | GOOD | 1 | 3049.9ms |
| RAG-27 | post_calibration_validation | AR | كيف أقدم شكوى رسمية بخصوص خطأ في الخدمة أو... | GOOD | 1 | 4169.4ms |
| RAG-28 | post_calibration_validation | EN | Does MediLab provide inpatient hospital ad... | NO_KNOWLEDGE | N/A (Correct) | 2887.2ms |

---

## Evidence Notes
1. Correctness target failures make this script exit non-zero.
2. The latency target is engineering-only and non-blocking; misses are reported honestly.
3. The post-calibration validation set is not an independent holdout because QA diagnostics inspected some cases.
4. Unsupported services must remain `NO_KNOWLEDGE` with zero final chunks.
