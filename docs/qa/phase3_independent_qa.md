# Phase 3 Independent QA Review

**Date:** 19 September 2026  
**Branch:** `feat/phase3-langgraph-core`  
**Base:** `main` @ `d177df7c024e07d9dabc6ab7c34d75bd5df80134`  
**Status:** **IN PROGRESS / CURRENT-HEAD EXECUTABLE VERIFICATION REQUIRED**

## Why this review exists

Antigravity produced a substantial Phase 3 implementation and a later Gemini/configuration hardening
pass. This independent review inspected the GitHub code rather than accepting the execution report at
face value. The review found several real correctness/evaluation gaps and pushed targeted fixes to the
same Phase 3 branch.

Historical Antigravity runtime evidence on SHA
`f225d4538e0c9c1fbed96fcc1c646a926341f2dc` included 172 unit tests, 38 PostgreSQL tests,
210 total tests, Ruff/format success, and a deterministic 42-case evaluation. A real Gemini
16-case evaluation did **not** complete: the configured Google API call returned HTTP 400 and the
runner correctly reported `BLOCKED` without falling back to fake.

Because independent QA changed executable code after that SHA, the historical pass counts are no
longer current-head signoff evidence.

## Findings and fixes

### 1. Agent environment limits were partly dead configuration

The `.env` contract exposed `MAX_INPUT_LENGTH`, `MAX_RECENT_MESSAGES`,
`MAX_CUSTOMER_BOOKINGS`, and `MAX_CLARIFICATION_ATTEMPTS`, but runtime nodes still used
hard-coded/default values.

Fixed:
- `input_guard` now reads `MAX_INPUT_LENGTH` from Flask config.
- `load_context` now reads `MAX_RECENT_MESSAGES` and `MAX_CUSTOMER_BOOKINGS`.
- customer-context loading receives the configured booking bound.
- `clarification_node` now reads `MAX_CLARIFICATION_ATTEMPTS`.
- regression tests prove configured input/clarification limits affect runtime behavior.

### 2. Unsupported/fabricated hotline

Clarification and Gemini fallback text contained a hard-coded customer-service phone number that was
not backed by repository business data.

Fixed:
- removed the invented number;
- fallback language now refers generically to MediLab customer service / nearest branch.

### 3. Semantic visible-reference resolution was still phrase-driven

Production reference resolution contained semantic keyword logic for phrases such as `full`,
`package`, and Arabic equivalents.

Fixed:
- exact ordinal positions remain deterministic;
- the LLM understanding pass receives the exact visible `SearchSnapshot` options;
- Gemini may propose `visible_item_id` / `visible_item_type` only from those options;
- deterministic code validates the proposed entity against the exact active snapshot before selection;
- non-visible proposals remain unresolved and re-enter clarification.

This keeps language interpretation LLM-driven while preserving deterministic reference integrity.

### 4. Hidden/special thyroid candidate injection

The clarification node had special production logic that manually appended a thyroid package for
thyroid wording.

Fixed:
- removed the special phrase branch;
- candidate options now come from the real catalog repositories using the LLM-extracted query;
- the saved `SearchSnapshot` is the exact set of options shown to the user.

### 5. Uncertainty could rely too heavily on LLM self-report

A broad extracted catalog query could proceed even when several real candidates matched.

Fixed:
- `uncertainty_gate` now treats multiple real catalog matches as deterministic ambiguity evidence;
- downstream structured lookup no longer silently chooses the first test from a multi-match result.

### 6. Price hallucination validator was not authoritative

The previous response validator could detect an unsupported price but leave the response valid.
It also did not robustly inspect list/nested structured results.

Fixed:
- customer-facing currency amounts must match price fields in verified structured SQL evidence;
- nested/list structured results are supported;
- a missing/unmatched SQL price invalidates and repairs the response;
- unit tests cover grounded, nested, hallucinated, and no-evidence price cases.

### 7. Provider/error secret hygiene

Unexpected safety/provider exceptions could be copied into graph state or traceback logs.

Fixed:
- safety-node unexpected errors use a generic fail-closed reason;
- raw exception text is not persisted by the node;
- provider-specific diagnostics remain sanitized inside `GeminiProvider`;
- unit Gemini provider failure is now simulated offline rather than hitting Google from unit tests.

### 8. RAG infrastructure failure was mislabeled as `NO_KNOWLEDGE`

An exception from retrieval previously became `NO_KNOWLEDGE`, incorrectly claiming the knowledge
base lacked an answer.

Fixed:
- retrieval exceptions become `RETRIEVAL_ERROR` / `CONTROLLED_ERROR`;
- no raw exception text is persisted;
- a customer-safe temporary-unavailable response is returned;
- legitimate `NO_KNOWLEDGE` remains semantically distinct.

### 9. Structured-data failures were uncontrolled

Database/service failures in `structured_data_node` could bubble out of the graph.

Fixed:
- structured read failures now become controlled, customer-safe unavailable responses;
- raw DB exception details are not exposed.

### 10. Combined-read failure propagation

A combined SQL+RAG request could hide a RAG failure behind the successful SQL half.

Fixed:
- combined reads propagate `CONTROLLED_ERROR` from either source;
- valid `NO_KNOWLEDGE` remains distinct from infrastructure failure.

### 11. Evaluation metrics were too permissive

The previous deterministic evaluator could overstate performance because:
- a correct route could count as a correct intent;
- unsafe categories were effectively inferred from expected labels;
- ordinal accuracy did not require the exact visible entity;
- associated customer history could be counted correct without proving isolation;
- per-case pass did not require every important metric;
- the evaluator did not explicitly bind itself to `TEST_DATABASE_URL`.

Fixed by rewriting `scripts/eval_phase3_agent.py`:
- deterministic benchmark explicitly uses `FakeLLMProvider`;
- it requires disposable `TEST_DATABASE_URL` and rejects Supabase / app DB equality;
- exact safety category is measured;
- intent is exact for safe requests that reach NLU (unsafe requests intentionally stop earlier);
- route and clarification checks are exact;
- ordinal selection must match the exact visible item id/type;
- customer-isolation cases prove own data appears and another synthetic customer's reference does not;
- all applicable checks must pass for a case to pass;
- evaluator success requires thresholds **and** all cases passing.

### 12. Live Gemini evaluator was also too permissive

Fixed by rewriting `scripts/eval_phase3_gemini_live.py`:
- asserts a real `GeminiProvider`;
- no fake fallback;
- corrected 16-case capability mix;
- exact safety category;
- exact intent on safe/NLU cases;
- exact route/clarification/fact checks;
- every case must pass in addition to aggregate thresholds;
- records real network/model latency including Avg/P50/P95/Min/Max.

### 13. Public turn result lacked exact safety category

Strict evaluators could not inspect the real safety category because `MediLabAgent.run_turn()` only
returned `is_safe`.

Fixed:
- `run_turn()` now exposes the structured `safety_classification` result for tests/evaluation.

## Important remaining verification work

The code fixes above have been pushed, but the branch must be re-executed on the new head.

Required commands:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/unit -v
uv run pytest -m postgres -v
uv run pytest -q
uv run python scripts/eval_phase3_agent.py
uv run python scripts/eval_phase3_gemini_live.py
```

The last command requires a working `GEMINI_API_KEY` with access to `gemini-2.5-flash`.
The previous Google request returned HTTP 400, so Phase 3 is not `LIVE_VERIFIED` until this succeeds.

## Signoff rule

Do not merge PR #4 or advance to Phase 4 until:

1. current-head automated suites pass;
2. the hardened deterministic evaluator passes;
3. a real Gemini evaluation completes successfully (not `BLOCKED`);
4. evidence/docs are regenerated against the current executable SHA.
