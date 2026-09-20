# Phase 3 Agent Evaluation Report

**Date:** 19 September 2026  
**Branch:** `feat/phase3-langgraph-core`  
**Dataset:** `evals/phase3_agent_cases.json` (42 cases)  
**Deterministic runner:** `scripts/eval_phase3_agent.py`  
**Real-LLM runner:** `scripts/eval_phase3_gemini_live.py`  

## Current verification status

Phase 3 is **IN PROGRESS / CURRENT-HEAD VERIFICATION REQUIRED**.

The last fully executed deterministic evidence was produced on SHA
`4cad42ec62973983f7d5d906555b61f6ac78c6ef` before the latest independent-QA executable changes:

- Ruff: PASS
- Format check: PASS
- Unit tests: **176 passed**
- PostgreSQL integration tests: **38 passed**
- Full suite: **214 passed**
- Strict deterministic benchmark: **42/42 passed**

Those numbers are now **historical regression evidence**, not signoff evidence for the newer branch
head. Independent QA subsequently changed graph routing, context hydration, Gemini prompting,
SearchSnapshot lifecycle, response validation, persistence, availability reads, testing isolation,
and the runtime verification script. A fresh execution is required before the new head may be called
`TESTED`.

Real Gemini verification is still **BLOCKED** by the locally configured credential. The last real
request reached `GeminiProvider` / `gemini-2.5-flash` without Fake fallback, but Google returned HTTP
400 `API_KEY_INVALID`. The repository cannot correct an untracked local credential; a valid Gemini API
key must be supplied locally and the real runner re-executed. Do not infer the exact credential type
from its text alone; the authoritative fact is that Google rejected it as invalid.

## Evaluation architecture

Phase 3 intentionally has two distinct evaluation tiers.

### Tier A — deterministic graph regression

```bash
uv run python scripts/eval_phase3_agent.py
```

- Provider: `FakeLLMProvider` test double
- Database: disposable PostgreSQL from `TEST_DATABASE_URL`
- Purpose: reproducible graph/state/business-truth regression
- Measures exact safety category, safe-request intent, route, clarification state, exact visible
  ordinal selection, session/customer isolation, action-boundary integrity, expected/prohibited
  facts, and graph latency
- This tier is **not** evidence of Gemini language-model accuracy

### Tier B — real Gemini evaluation

```bash
uv run python scripts/eval_phase3_gemini_live.py
```

- Provider: `GeminiProvider` only
- Model: configured `LLM_MODEL` (currently `gemini-2.5-flash`)
- No fake fallback permitted
- Measures real provider behavior and network/model latency
- A successful run is required before Phase 3 may be called `LIVE_VERIFIED`

The separate multi-turn verifier:

```bash
uv run python scripts/verify_agent_live.py --real-llm
```

now runs against **disposable `TEST_DATABASE_URL` only**, so QA fixtures can never be written into the
Supabase/application database. Without `--real-llm` it uses the deterministic test provider on the
same disposable database.

## Independent-QA hardening after SHA `4cad42e`

The current branch adds/fixes:

- customer-history + policy/SQL **multi-source** routing instead of letting the history route eclipse
  RAG/structured evidence;
- bounded recent conversation, selected entity labels, visible options, and privacy-minimized customer
  history supplied to Gemini understanding;
- Gemini safety classification now receives bounded recent context;
- technical provider error details are logged only after sanitization and are not copied into durable
  conversational state;
- clarification wording remains LLM-driven while Python renders the exact numbered business options
  that are saved in the `SearchSnapshot`;
- one active visible snapshot per session; previous active snapshots become `STALE` and stale snapshots
  cannot resolve ordinals/semantic references;
- response validation requires an explicit `{success: true, committed: true}` action result before any
  customer-facing mutation success claim;
- malformed session IDs are never persisted as durable conversation rows;
- pending actions and meaningful `last_updated_at` / `last_turn_latency_ms` state are persisted;
- test configuration always uses FakeLLM by default even if a developer `.env` contains Gemini
  credentials, preventing accidental Google calls from ordinary pytest runs;
- structured missing-data is distinguished from infrastructure failure;
- current availability slots can be read from the authoritative `BranchService`;
- `.env.example` clarifies that `GEMINI_API_KEY` must be a valid Gemini API credential and not an OAuth
  client/project identifier;
- multi-turn verification no longer writes synthetic QA history into the durable application database.

## Dataset provenance

The 42 cases use `calibration` and `post_implementation_validation` labels. The latter are **not an
independent holdout** because developers have inspected and modified the cases during hardening.
Describe them as post-implementation regression/validation cases only.

## Final acceptance gate

Run on the final code SHA:

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/unit -v
uv run pytest -m postgres -v
uv run pytest -q
uv run python scripts/eval_phase3_agent.py
uv run python scripts/verify_agent_live.py
uv run python scripts/eval_phase3_gemini_live.py
uv run python scripts/verify_agent_live.py --real-llm
```

Critical targets remain engineering targets, not official assessment weights:

- safety category accuracy: 100%
- customer/session isolation: 100%
- no unsupported action-success claims: 100%
- exact visible-reference resolution: 100%
- safe-request intent accuracy: >= 90%
- route accuracy: >= 90%
- clarification decision accuracy: >= 90%
- fact grounding: >= 90%
- real Gemini run: successful, with no fake fallback

Do not copy historical counts onto a newer SHA. Record actual counts, failures, and latency after the
fresh run.

## Conclusion

The latest code contains additional correctness and privacy hardening beyond the last 214-test / 42-case
execution. Therefore the branch remains **IN PROGRESS** until those gates are rerun on the final head and
real Gemini succeeds with a valid local credential.
