# Phase 3 Independent QA Review

**Date:** 19 September 2026  
**Branch:** `feat/phase3-langgraph-core`  
**Base:** `main` @ `d177df7c024e07d9dabc6ab7c34d75bd5df80134`  
**Status:** **IN PROGRESS / CURRENT-HEAD EXECUTABLE VERIFICATION REQUIRED**

## Evidence boundary

Antigravity's final executed pass on SHA `4cad42ec62973983f7d5d906555b61f6ac78c6ef`
reported Ruff/format success, **176 unit tests**, **38 PostgreSQL tests**, **214 full-suite tests**, and
**42/42 deterministic evaluation cases**. Its real Gemini request reached `GeminiProvider` but Google
returned HTTP 400 `API_KEY_INVALID`, so real Gemini remained blocked.

Independent QA then changed executable code again. Therefore the `4cad42e` results are historical and
must not be described as current-head evidence. The new head requires a complete rerun.

## First independent-QA fixes already retained

The branch retains the earlier hardening for:

- `.env` limits wired to runtime behavior;
- removal of an unsupported hard-coded customer-service number;
- LLM-proposed semantic visible references with deterministic snapshot verification;
- removal of hidden/special thyroid candidate injection;
- deterministic multi-candidate ambiguity checking;
- authoritative rejection of hallucinated prices;
- sanitized provider/error handling and fail-closed safety;
- RAG infrastructure failure distinct from `NO_KNOWLEDGE`;
- controlled structured-data errors;
- combined SQL+RAG error propagation;
- stricter deterministic/live evaluation semantics;
- exact safety classification exposed by `MediLabAgent.run_turn()`.

## Second independent-QA findings and fixes

### 1. Customer history eclipsed RAG/SQL in compound questions

A validated plan with `requires_customer_history=true` returned the history branch before considering
`requires_rag` or `requires_structured_data`. That prevented questions such as "what did I book and
what is the cancellation policy?" from gathering both sources.

Fixed:
- added `multi_source_node`;
- router now sends history+RAG and history+SQL plans to the multi-source read path;
- no mutation capability is introduced.

### 2. The understanding LLM did not receive enough durable conversational context

The previous context summary exposed IDs/flags but omitted recent conversation, selected entity labels,
and bounded historical booking facts.

Fixed:
- Gemini receives bounded recent messages;
- selected test/package names/codes are hydrated from PostgreSQL;
- a privacy-minimized customer-history summary is available for contextual reasoning;
- phone number, customer name, and internal customer ID are not sent in that summary;
- exact active visible options remain available for semantic reference interpretation.

### 3. Safety classification accepted recent context but ignored it

Fixed:
- Gemini safety input now includes bounded recent role/content context plus the current message;
- errors still fail closed using a generic durable reason;
- sanitized technical details remain internal logs only.

### 4. SearchSnapshot contents were not guaranteed to equal what the customer visibly saw

The database snapshot stored candidates while the LLM independently worded the clarification. That
could theoretically reorder or omit options, making "the second one" ambiguous relative to the stored
sequence.

Fixed:
- LLM generates the natural clarification question only;
- Python appends the exact numbered candidate list in the exact stored order;
- snapshot items include explicit visible `position`;
- pending clarification stores the exact visible candidate IDs/types/names and snapshot ID.

### 5. Stale snapshot lifecycle was incomplete

Fixed:
- context hydration ignores non-`ACTIVE` snapshots;
- resolver rejects stale snapshots for ordinal/semantic selection;
- creating a new snapshot marks the previous active one `STALE`;
- repository guarantees monotonically increasing sequence numbers and one active visible snapshot per
  session.

### 6. Testing could inherit a real Gemini provider from a developer `.env`

This had already caused an integration path to accidentally attempt Google in an earlier pass.

Fixed at the root:
- `TestingConfig.as_mapping()` forces `LLM_PROVIDER=fake` and clears `GEMINI_API_KEY`;
- explicit `test_config` can still opt into Gemini for a dedicated live test;
- regression coverage verifies ambient Gemini environment values cannot leak into ordinary pytest.

### 7. A non-null failed action result could authorize a fake success sentence

Fixed:
- response success claims now require explicit `success is True` **and** `committed is True`;
- a failed/non-committed result is treated the same as no successful action truth;
- regression tests cover failed and committed-success results.

### 8. Invalid session IDs could still create durable rows during the persistence tail

The input guard rejected them, but `persist_context` still ran later in the graph.

Fixed:
- persistence revalidates the session identifier before any database write;
- invalid IDs return without creating a session/message;
- `pending_action` is now durably persisted;
- `current_state` now records `last_updated_at` and `last_turn_latency_ms` instead of using latency as a
  pseudo turn timestamp.

### 9. Structured missing-data and availability reads were incomplete

Fixed:
- genuine structured no-match becomes `NO_KNOWLEDGE` rather than an empty `ANSWER`;
- service/DB exceptions remain `CONTROLLED_ERROR` with no raw error leakage;
- `AVAILABILITY` can read current available slots through the authoritative `BranchService`, returning
  slot/branch/date/time/remaining-capacity facts from SQL.

### 10. Verification script could write synthetic QA fixtures into the application DB

Fixed:
- `scripts/verify_agent_live.py` now requires and validates `TEST_DATABASE_URL`;
- it refuses Supabase / app-DB equality;
- deterministic and real-Gemini verification both use disposable PostgreSQL;
- synthetic customer/history fixtures are created only there;
- real mode explicitly requires `GeminiProvider` and never falls back to fake.

### 11. Gemini credential documentation over-asserted credential type

Google's authoritative observed result is simply `API_KEY_INVALID`. The repository cannot prove the
exact type of the invalid local string merely from its prefix.

Fixed:
- `.env.example` now says `GEMINI_API_KEY` must be a valid Gemini/Generative Language API credential;
- it warns not to place OAuth client IDs or project identifiers in that field;
- no secret or prefix is committed.

## Tests added/expanded in the second pass

New/expanded coverage includes:

- history+RAG and history+SQL routing;
- multi-source evidence preservation;
- privacy-minimized conversational context passed to the LLM;
- stale snapshot rejection;
- one-active-snapshot lifecycle;
- exact numbered clarification rendering;
- test-environment isolation from ambient Gemini configuration;
- failed action result cannot authorize success;
- pending-action persistence and invalid-session persistence guard;
- structured no-answer and controlled failure;
- authoritative availability-slot read.

## CI observation

GitHub Actions runs associated with the branch have repeatedly shown the unit job failing before any
steps execute, with the PostgreSQL job skipped. This is not application test evidence and must not be
reported as CI PASS. Local/Antigravity execution evidence remains the executable source until the
GitHub-hosted runner starts normally.

## Required current-head execution

Run after pulling the final branch head:

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

The last two real-provider commands require a valid local `GEMINI_API_KEY` accepted by Google for the
configured model.

## Signoff rule

Do not merge PR #4 or advance to Phase 4 until:

1. current-head Ruff/format/unit/PostgreSQL/full-suite gates pass;
2. the strict 42-case deterministic evaluator passes on the same executable SHA;
3. disposable-DB multi-turn verification passes;
4. real Gemini evaluation and real Gemini multi-turn verification complete successfully with no fake
   fallback;
5. README / PR evidence is updated to those final results.
