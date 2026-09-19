# Phase 3 Real Gemini Hardening Review

**Date:** 20 September 2026  
**Branch:** `feat/phase3-langgraph-core`  
**Status:** IN PROGRESS — current-head rerun required

## Evidence from first paced real-Gemini run

The Gemini credential is now accepted by Google. After adding free-tier pacing and honoring `LLM_MAX_RETRIES=0`, the real provider run completed without HTTP 429 rate-limit failures.

Observed runtime:

- provider: `GeminiProvider`
- model used by the local run: `gemini-3.5-flash-lite`
- HTTP 429 count: 0
- no FakeLLM fallback

The first 16-case real run was **not** accepted as LIVE_VERIFIED. It exposed application/provider-integration behavior that deterministic FakeLLM tests could not reveal:

1. Gemini sometimes returned harmless JSON representation variations for `RequestPlan` fields, including a scalar `requested_information`, `{}` for an empty `references` list, and `false` for an absent `action_intent`. Strict Pydantic validation correctly rejected those shapes, but the fallback turned otherwise understandable requests into `UNKNOWN_AMBIGUOUS`.
2. The live safety classifier over-classified some catalog and non-clinical out-of-domain requests as clinical unsafe requests.

## Current-head fixes

The current branch adds:

- an explicit JSON type contract in the Gemini request-understanding prompt;
- bounded representation-only normalization before Pydantic validation;
- scalar string → one-item list normalization for list fields;
- empty object → empty list normalization only for list fields where the object is empty;
- `action_intent=false` → `null` normalization;
- common language labels → `en` / `ar` / `mixed` normalization;
- non-empty malformed object structures remain invalid and still fail safely;
- clearer clinical-safety semantics distinguishing catalog browsing from symptom-driven medical test recommendation;
- explicit handling that non-clinical out-of-domain/prompt-injection content is not itself a clinical-safety violation;
- regression tests covering normalization and the safety prompt boundary.

The architecture remains:

> LLM understands. Python verifies. LLM explains.

No deterministic keyword router was introduced. Python normalization only repairs unambiguous JSON representation drift; Pydantic remains the authoritative structured-output validator.

## Required verification

Because executable code changed after the 232-test pass, rerun on the latest head:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run python scripts/eval_phase3_agent.py
uv run python scripts/verify_agent_live.py

$env:LLM_MAX_RETRIES="0"
$env:GEMINI_LIVE_PACING_SECONDS="16"
uv run python scripts/eval_phase3_gemini_live.py
uv run python scripts/verify_agent_live.py --real-llm
```

Do not mark Phase 3 LIVE_VERIFIED until both real-Gemini commands pass on the same final executable SHA with no FakeLLM fallback.
