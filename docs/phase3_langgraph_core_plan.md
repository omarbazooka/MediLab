# MediLab AI — Phase 3 LangGraph Core & Conversation Loop Plan

## Status

- **Classification:** Required / Core
- **Phase:** Phase 3 — LangGraph Core + Conversation Loop
- **Branch:** `feat/phase3-langgraph-core`
- **Base:** Phase 2 squash merge `d177df7c024e07d9dabc6ab7c34d75bd5df80134`
- **Phase 2 status:** TESTED + LIVE_VERIFIED
- **Deadline:** 20 September 2026
- **Current milestone:** M3.1 — State / Context

## Goal

Build one meaningful LangGraph `StateGraph` orchestrator around the independently tested SQL/RAG/business services. LangGraph coordinates control flow; PostgreSQL remains durable truth and deterministic services remain authoritative for IDs, validation, references, transactions, and success/failure.

The target graph is:

```text
START
→ input_guard
→ load_context
→ safety_gate
→ understand_request
→ resolve_pending_context
→ uncertainty_gate
    ├─ uncertain → clarification_node → persist_context → END TURN
    └─ clear → router
         ├─ structured_data_node
         ├─ RAG path
         ├─ action path (Phase 4 implementation)
         └─ general
→ compose_response
→ response_validator
→ persist_context
→ END
```

Phase 3 must visibly branch and must prove that clarification can suspend one turn and resume on the next graph run.

## Scope boundary

### Included in Phase 3

- typed graph state
- input validation/normalization
- durable conversation/session context loading
- healthcare safety classification and safe response path
- request intent/entity understanding through a configurable LLM interface
- deterministic pending-context merge/resume behavior
- uncertainty/clarification gate
- pending clarification persistence
- bounded clarification attempts
- structured-data routing
- integration of the existing standalone Phase 2 `RAGService`
- general-response path
- response validation
- conversation/message/current-state persistence
- graph routing tests with deterministic LLM stubs
- PostgreSQL session isolation / clarification-resume integration tests

### Deferred to Phase 4

- branch booking graph mutation flow
- home visit graph mutation flow
- explicit action confirmation machinery
- pending-action field collection beyond the Phase 3 state/interface boundary
- booking-status/cancellation tool execution through the graph

Existing deterministic business services remain available but are not moved into Phase 3 prematurely.

## Data ownership

### PostgreSQL durable truth

- `ConversationSession`
- `ChatMessage`
- current structured state
- selected test/package
- active `SearchSnapshot`
- pending clarification
- pending action interface state

### Graph state

Per-run orchestration state only. It is hydrated from PostgreSQL at the start of a turn and persisted back before the turn ends.

### LLM responsibilities

- intent classification
- entity extraction
- ambiguity indicators
- clarification wording where useful
- natural response composition

The LLM must not invent database IDs, prices, availability, booking success, source citations, or missing business facts.

## Agent state target

`MediLabAgentState` should contain only data needed for orchestration, including:

- `session_id`
- `user_message`
- recent messages / loaded context
- `intent`
- `intent_confidence` or equivalent evidence field
- `entities`
- unresolved / ambiguous entities
- selected test/package IDs
- active search snapshot
- `needs_clarification`
- pending clarification
- clarification reason / attempts
- pending action interface state
- missing fields
- rewritten RAG query
- retrieval attempt / chunks / quality
- structured result
- tool result placeholder
- safety flag / reason
- response
- controlled errors

Avoid process-global mutable state.

## Milestone 3.1 — State / Context

Required implementation:

- [ ] add `langgraph` dependency and lock it with `uv`
- [ ] `MediLabAgentState`
- [ ] graph package/module layout
- [ ] `input_guard`
- [ ] `load_context`
- [ ] `safety_gate`
- [ ] configurable request-understanding interface
- [ ] `understand_request`
- [ ] `resolve_pending_context`
- [ ] deterministic unit tests for each node
- [ ] no DB schema migration unless current models demonstrably cannot persist required state

Acceptance:

- empty/oversized input is controlled
- existing session state loads without process memory
- service/preparation requests pass safety
- diagnosis/result-interpretation/medication requests route to the safety boundary
- structured understanding output is deterministic under stubbed LLM tests
- a previous pending clarification can be loaded and merged with the next user turn

## Milestone 3.2 — Clarification

- [ ] uncertainty gate
- [ ] ambiguous entity/reference handling
- [ ] one focused clarification question
- [ ] persistent pending clarification
- [ ] end current graph turn after asking
- [ ] next user turn resumes through a new graph invocation
- [ ] clarification attempts bounded (target maximum 2 for the same unresolved concept)
- [ ] safe fallback/human support after bound is reached

Missing action fields and semantic ambiguity may use the same mechanism, but must remain distinguishable in state/reason fields.

## Milestone 3.3 — Routing / Responses

- [ ] router with explicit branches
- [ ] structured-data branch using existing services/repositories
- [ ] RAG branch using existing Phase 2 `RAGService`
- [ ] action branch boundary/placeholder for Phase 4 (no fake mutations)
- [ ] general response
- [ ] compose response from verified facts/context only
- [ ] response validator
- [ ] persist messages/current state
- [ ] graph builder / compiled graph entry point

Acceptance:

- graph topology is meaningful and inspectable
- structured query reaches SQL path
- preparation/policy question reaches RAG path
- clinical request reaches safety path
- ambiguous request suspends and resumes on the next turn
- persistence/session isolation is proven on PostgreSQL

## Intent baseline

Initial intent families should cover at least:

### Structured
- test search/details/price
- package search/details/price
- branch information
- availability

### RAG
- preparation
- policy/FAQ
- home-visit information
- cancellation/rescheduling policy

### Action boundary
- branch booking
- home visit booking
- booking status
- cancellation

### Safety/general
- medical-advice request
- result interpretation
- general conversation
- unknown

Intent changes must be reflected in tests and docs.

## Clarification rules

- never guess when intent/entity/reference meaning is uncertain
- ask exactly one targeted question per clarification turn
- persist pending clarification before ending the turn
- resume on the next user message through a fresh graph run
- use current explicit state before recent history and older context
- ordinal references resolve only against the active visible `SearchSnapshot`
- hidden DB rows/history must never change visible positions

## Safety rules

MediLab is not clinical decision support.

The graph must not diagnose, clinically interpret laboratory results, prescribe/recommend medication, recommend medically necessary tests based on symptoms, or provide emergency triage. Clinical requests receive a controlled boundary response directing the user to a qualified healthcare professional.

## Testing plan

### Unit

- state construction/defaults
- input guard
- safety categories
- request-understanding schema/parse failure
- pending clarification merge
- uncertainty routing
- clarification attempt bound
- router branch for every major path
- response validator
- deterministic reference resolution where introduced

### PostgreSQL integration

- new session
- existing session hydration
- recent message ordering
- current state persistence
- session isolation
- pending clarification persistence
- next-turn clarification resume
- active snapshot/reference behavior

### Graph integration

Use deterministic LLM stubs first:

- structured query → structured branch
- policy/preparation query → RAG branch
- unsafe clinical query → safety path
- ambiguous query → clarification → END
- next turn → load pending clarification → resume
- LLM failure → controlled fallback

### Live verification before Phase 3 completion

At least one real LLM + LangGraph flow must prove:

1. natural-language request,
2. durable session context,
3. meaningful graph routing,
4. RAG retrieval on the existing live corpus,
5. clarification/follow-up across two turns,
6. controlled response validation/persistence.

Business mutation proof remains Phase 4.

## Deadline / risk assessment

Deadline risk is high because the assessment is due 20 September 2026. Keep Phase 3 narrow:

- no supervisor/multi-agent architecture
- no Redis/checkpoint infrastructure unless current PostgreSQL state cannot satisfy a required behavior
- no sophisticated learned router before deterministic/stubbed graph works
- no Phase 4 mutation workflow inside Phase 3
- no frontend redesign
- no RAG redesign

Required LangGraph control flow, durable clarification, RAG integration, tests, and interview explainability outrank optional polish.

## Definition of Done

Phase 3 becomes TESTED only when automated graph/unit/PostgreSQL tests pass on the final code SHA.

Phase 3 becomes LIVE_VERIFIED only when a real LLM graph run proves meaningful routing + durable multi-turn clarification + live RAG while respecting the safety boundary.

Until then, Phase 3 status is **IN_PROGRESS**.
