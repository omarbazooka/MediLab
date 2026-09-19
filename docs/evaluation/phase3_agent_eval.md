# Phase 3 Agent Evaluation Report

**Date:** 19 September 2026  
**Branch:** `feat/phase3-langgraph-core`  
**Dataset:** `evals/phase3_agent_cases.json` (42 cases)  
**Deterministic runner:** `scripts/eval_phase3_agent.py`  
**Real-LLM runner:** `scripts/eval_phase3_gemini_live.py`  

## Current verification status

Phase 3 is **IN_PROGRESS / STATUS NEEDS VERIFICATION** after an independent QA hardening pass.

Antigravity previously executed the automated suites and deterministic benchmark on code SHA
`f225d4538e0c9c1fbed96fcc1c646a926341f2dc`. Those results are retained below as historical
runtime evidence. Independent QA subsequently changed executable agent/evaluator code, so those
numbers must not be described as current-head results until the final branch head is rerun.

The real Gemini benchmark is also still **BLOCKED**: the latest recorded attempt reached
`GeminiProvider` with model `gemini-2.5-flash` but Google returned HTTP 400. The runner correctly
failed closed and did not fall back to `FakeLLMProvider`.

## Evaluation architecture

Phase 3 intentionally has two different evaluation tiers.

### Tier A — deterministic graph regression

`uv run python scripts/eval_phase3_agent.py`

- Provider: `FakeLLMProvider` (test double only)
- Database: **must be `TEST_DATABASE_URL`**, a disposable PostgreSQL database
- Purpose: repeatable graph/state/business-grounding regression
- Covers exact safety category, safe-request intent, graph route, clarification state, exact visible
  ordinal selection, customer/session isolation, action-boundary integrity, expected/prohibited facts,
  and graph latency.
- This benchmark is **not** evidence of Gemini language-model accuracy.

Independent QA tightened this runner after discovering that the earlier implementation could
inflate metrics (for example, counting a correct route as a correct intent and not requiring every
applicable check for a case pass). The hardened runner now requires the relevant checks directly and
returns failure if any case fails.

### Tier B — real Gemini evaluation

`uv run python scripts/eval_phase3_gemini_live.py`

- Provider: `GeminiProvider` only
- Model: `gemini-2.5-flash`
- No fake fallback is permitted
- Focused 16-case set covers English, Arabic, mixed-language input, structured SQL, RAG,
  combined SQL+RAG, ambiguity/clarification, medical-safety boundaries, prompt injection,
  general conversation, and controlled out-of-domain handling.
- Measures real provider safety, safe-request intent, route, clarification, response grounding,
  and real network/model latency.

A successful run of this tier is required before Phase 3 can be called `LIVE_VERIFIED`.

## Historical automated evidence — SHA `f225d4538e0c9c1fbed96fcc1c646a926341f2dc`

Before the independent QA code changes, Antigravity recorded:

- Unit tests: **172 passed**
- PostgreSQL integration: **38 passed**
- Full suite: **210 passed**
- Ruff: **PASS**
- Format check: **PASS**
- 42-case deterministic benchmark: reported **100%** across its then-current metrics

These results establish a useful historical baseline, but the evaluator itself was subsequently
hardened and executable code changed. They are not current-head signoff evidence.

The earlier deterministic latency numbers (sub-millisecond understanding/composition timings) came
from `FakeLLMProvider`; they must never be presented as Gemini latency.

## Independent QA changes requiring a fresh run

The independent review hardened several areas that materially affect verification:

- Gemini-only configuration and no silent fake fallback
- safety-provider fail-closed behavior and secret sanitization
- configured input/context/clarification bounds wired into runtime behavior
- semantic visible-option references interpreted by the LLM but deterministically validated against
  the exact active `SearchSnapshot`
- multiple real catalog candidates trigger clarification rather than first-row selection
- hallucinated currency amounts are blocked unless present in verified structured SQL facts
- RAG infrastructure failure is separated from a legitimate `NO_KNOWLEDGE` result
- structured-data failure returns a controlled response rather than leaking raw exceptions
- deterministic evaluator uses the disposable test DB and strict per-case checks
- live Gemini evaluator uses exact provider/safety/intent/route checks and real latency measurements

## Dataset splits

The 42 cases use labels such as `calibration` and `post_implementation_validation`.

The validation cases are **not an independent holdout**: developers have inspected and modified the
evaluation data during hardening. They should therefore be described as post-implementation
validation/regression cases, not as evidence of unbiased generalization.

## Current acceptance gate

Before Phase 3 signoff, run on the final code SHA:

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

Required critical targets:

- safety category accuracy: 100%
- customer/session isolation: 100%
- no unsupported action-success claims: 100%
- visible ordinal resolution: 100%
- safe-request intent accuracy: >= 90%
- route accuracy: >= 90%
- clarification decision accuracy: >= 90%
- fact grounding: >= 90%
- real Gemini run: must execute successfully with no fake fallback

Record actual counts, failures, and latency from the final run. Do not copy the historical numbers if
they are not reproduced.

## Conclusion

The architecture and historical deterministic evidence are strong, but Phase 3 is not yet signed off
on the current head. Current-head automated reruns plus a successful real Gemini evaluation are the
remaining verification gates before merge.
