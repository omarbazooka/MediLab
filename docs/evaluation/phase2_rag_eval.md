# MediLab AI — Phase 2 Hybrid RAG Evaluation Report

## Metadata
- **Date / Time:** 2026-09-17 15:29:26 UTC
- **Git Commit SHA:** `8c73c4f843c1`
- **Database Endpoint:** `aws-1-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require`
- **Embedding Provider:** Jina AI
- **Embedding Model:** `jina-embeddings-v3`
- **Vector Dimension:** `384`
- **Evaluation Cases:** 20 cases (15 calibration, 5 independent holdout)

---

## Executive Summary Metrics (Split Breakdown)

### 1. Calibration vs Holdout Comparison

| Split | Cases | Recall@4 | MRR | No-Answer Accuracy | Retry Rate | Avg Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Calibration Set** | 15 | **100.0%** (12/12) | **1.0000** | **100.0%** | 13.3% | 2882.1ms |
| **Independent Holdout** | 5 | **100.0%** (4/4) | **1.0000** | **100.0%** | 20.0% | 2032.5ms |
| **Combined Overall** | 20 | **100.0%** (16/16) | **1.0000** | **100.0%** | 15.0% | 2669.7ms |

### 2. Benchmark Target Evaluation

| Metric | Measured Value | Benchmark Target | Status |
| :--- | :--- | :--- | :--- |
| **Recall@4** | **100.0%** (16/16) | >= 90.0% | **PASS** |
| **MRR (Mean Reciprocal Rank)** | **1.0000** | >= 0.8500 | **PASS** |
| **No-Answer Accuracy** | **100.0%** (4/4) | 100.0% | **PASS** |
| **Retry Rate** | **15.0%** (3/20) | <= 20.0% | **PASS** |
| **P95 Latency (Internal SLA)** | **5098.9ms** | < 500.0ms | **TARGET MISSED / NEEDS OPTIMIZATION** |
| **Median (P50) Latency** | **2853.4ms** | Operational SLA | Informational |
| **Average Total Latency** | **2669.7ms** | Operational SLA | Informational |
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
| RAG-16 | holdout | EN | How many hours before an in-clinic appoint... | GOOD | 1 | 1745.2ms |
| RAG-17 | holdout | AR | هل خدمة الزيارة المنزلية لسحب العينات متوف... | GOOD | 1 | 3196.3ms |
| RAG-18 | holdout | EN | When are standard CBC blood test results d... | GOOD | 1 | 1783.6ms |
| RAG-19 | holdout | AR | هل مسموح بشرب القهوة أو الشاي قبل تحليل ال... | GOOD | 1 | 987.7ms |
| RAG-20 | holdout | EN | Can MediLab administer chemotherapy infusi... | NO_KNOWLEDGE | N/A (Correct) | 2449.6ms |

---

## Analysis & Domain Safety
1. **Evaluation Split Integrity:** The benchmark explicitly separates the 15 calibration queries used during threshold tuning from the 5 independent holdout queries created after freezing thresholds. Performance generalizes across both sets.
2. **Deterministic No-Answer:** Queries requesting unsupported procedures (MRI, CT scans, surgery, chemotherapy infusions) consistently yield `NO_KNOWLEDGE` without fabricating laboratory offerings.
3. **Latency Profiling & Honest Target Assessment:**
   - Internal project target of hybrid retrieval P95 < 500ms is currently **MISSED** (measured P95: ~5098.9ms).
   - Analysis indicates this latency is predominantly driven by public WAN round-trip latency to the external Jina AI Embeddings API (~700-1500ms) and cloud Supabase PostgreSQL connection (~300-800ms) from the Windows development environment.
   - Core algorithmic execution (RRF fusion, signal-based grading, context assembly) takes < 2ms locally.
