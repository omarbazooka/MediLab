# MediLab AI — Phase 3 LLM Behavior, Customer Context & Catalog Knowledge Contract

## Classification

- **LLM-first conversational behavior:** Required / Core for Phase 3
- **Customer historical context in agent reasoning:** Core Enhancement to Phase 3 context loading
- **Complete non-clinical test catalog explanations:** Core Enhancement using the existing `LabTest` catalog
- **Business-policy enforcement for mutations:** Phase 4 deterministic enforcement; Phase 3 may explain/apply policy informationally

Deadline risk is controlled by reusing existing PostgreSQL models, `LabTest.short_description`, conversation/customer relations, and Phase 2 RAG. Avoid schema changes unless the existing model demonstrably cannot represent a required fact.

## 1. The agent must NOT behave like a rule-based chatbot

MediLab should not be implemented as a large tree of hard-coded user phrases, fixed questions, regex-based intent routing, or canned responses.

The intended interaction model is:

```text
User natural-language input
→ load durable context + relevant customer history
→ LLM structured understanding
→ LangGraph routing
→ deterministic SQL/RAG/business services obtain trusted facts
→ LLM response composition using those verified facts + conversation context
→ response validation
→ persist
```

The LLM is responsible for understanding natural language and producing natural language. Python is responsible for trustworthy execution and boundaries.

### LLM responsibilities

- infer intent from arbitrary Arabic/English/mixed-language phrasing
- extract entities and references
- understand follow-up language from recent/durable context
- identify semantic ambiguity
- generate one contextual clarification question when required
- synthesize verified SQL facts, RAG policy/process knowledge, relevant customer history, and prior conversation into a natural response
- vary wording naturally; no canned-response requirement

### Deterministic responsibilities

Deterministic code remains authoritative for:

- database IDs and entity existence
- prices and current structured catalog facts
- live branch/slot availability
- exact visible ordinal resolution from `SearchSnapshot`
- customer/booking ownership
- booking/action required fields
- transaction success/failure
- idempotency and duplicate prevention
- final mutation eligibility where a business policy blocks/allows an action
- success claims after commit

This separation prevents the system from becoming rule-based conversationally while still preventing the LLM from fabricating business truth.

## 2. No hard-coded user questions or fixed response templates

Do not implement routing such as:

```python
if "fast" in message:
    intent = "TEST_PREPARATION"
```

or large lists of exact customer utterances as production logic.

Test fixtures may contain fixed example utterances for deterministic testing, but production understanding must accept previously unseen phrasing through the configurable LLM understanding layer.

Safety may use deterministic validation/guardrails as a defense layer, but clinical-intent understanding should also be available to the LLM structured-output layer rather than relying on a keyword list alone.

Response composition should normally be performed by the LLM from verified context. Deterministic fallback messages are allowed only for controlled infrastructure/error/safety fallback when the LLM cannot be used safely.

## 3. LLM both before and after the tool/retrieval journey

The normal successful path should use the LLM twice conceptually:

### Understanding pass

Input includes:

- current user message
- recent conversation
- durable current state
- selected test/package
- active visible snapshot summary where relevant
- pending clarification/action context
- relevant customer-history summary where appropriate

Output is structured and validated, for example:

```json
{
  "intent": "TEST_DETAILS",
  "entities": {"test_query": "thyroid"},
  "references": [],
  "ambiguities": [],
  "needs_clarification": false
}
```

### Composition pass

After SQL/RAG/action-path execution, the LLM receives only trusted context required for the answer:

- verified structured facts
- grounded RAG excerpts/source metadata
- relevant customer-history facts
- tool result (when Phase 4 is active)
- current conversation state
- safety/response constraints

It then writes the customer-facing answer naturally in the user's language/style.

The LLM must not override failed tool results, invent missing facts, or claim an action happened when deterministic code says it did not.

## 4. Customer historical context

`ConversationSession.customer_id` links a conversation to the customer. Phase 3 `load_context` should be designed to include an intentionally bounded customer-context view when identity is resolved.

Useful history may include:

- recent bookings / visits
- recent booked test/package IDs and names
- booking status
- recent cancellations
- relevant dates/times
- currently selected service
- recent conversation facts

Do NOT indiscriminately dump the customer's entire database history into the prompt. Build a small purpose-specific context object and retrieve only what is relevant to the current request.

### Example policy reasoning

If an approved MediLab operational policy says a service cannot be repeated within a defined period, and the verified customer history shows a conflicting recent service:

```text
SQL customer history
+
RAG/structured approved policy
→ trusted policy evaluation inputs
→ LLM explains the situation naturally
```

However:

- do not invent such a policy;
- do not infer a medical restriction from general health knowledge;
- if the rule is clinical/medical, direct the user to a qualified healthcare professional rather than enforcing an invented clinical decision;
- if the rule affects a booking mutation, Phase 4 deterministic validation must enforce the final allow/block result. The LLM only explains it.

This preserves conversational intelligence without allowing an LLM interpretation to become authoritative transaction logic.

## 5. Test catalog explanations

Every active lab test in the MediLab catalog must have enough trusted content for the agent to answer questions such as:

- "What is TSH?"
- "What does CBC check?"
- "What is the difference between these thyroid tests?"
- "How much is it?"
- "What sample does it need?"
- "When should the result be ready?"
- "Do I need any preparation?"

The existing `LabTest` model already contains:

- code
- name
- category
- `short_description`
- sample type
- price
- result turnaround
- active status

Therefore Phase 3 should use SQL as the authoritative source for catalog identity, price, sample type, turnaround, and concise non-clinical description.

Detailed preparation/process guidance remains RAG-owned and can be combined with the structured catalog answer.

### Content-quality requirement

Review the seeded descriptions for all active tests before Phase 3 signoff. Rewrite descriptions that sound like diagnosis, medical interpretation, or symptom-based recommendation. They should explain the test in customer-friendly, non-clinical terms.

Preferred style:

> "TSH is a blood test that measures thyroid-stimulating hormone, a hormone involved in regulating thyroid function. MediLab can explain the test process, price, sample type, and preparation requirements, but medical interpretation belongs to a qualified healthcare professional."

Avoid wording that tells the customer what condition they have or which test they medically need.

## 6. Ambiguous test selection

When a user says something broad such as:

> "I want a thyroid test."

The LLM may understand the category/topic, but it must not invent a single selected test if several active catalog items plausibly match.

The system should:

1. query the real catalog;
2. expose relevant options with concise descriptions/prices as appropriate;
3. persist the visible `SearchSnapshot`;
4. let the LLM ask a natural clarification question;
5. resolve "the first/second one" deterministically against that exact visible snapshot.

If choosing between tests would require clinical judgment or symptom-based recommendation, explain the available tests at a high level and direct the user to MediLab customer support or a qualified healthcare professional rather than selecting medically on the user's behalf.

## 7. Context priority

Prompt/context assembly must respect:

```text
current explicit user statement
> current structured state
> relevant verified customer history
> recent messages
> optional summary
> old history
```

Old history must not override a new explicit correction from the user.

## 8. Response composition contract

The response composer should receive typed/structured evidence, not raw uncontrolled database objects.

Suggested conceptual input:

```json
{
  "user_message": "...",
  "intent": "...",
  "conversation_context": {},
  "customer_context": {},
  "structured_facts": {},
  "rag_context": [],
  "tool_result": null,
  "safety_constraints": [],
  "response_goal": "answer | clarify | safe_boundary | no_knowledge"
}
```

The final response should be natural and context-sensitive, not a fixed template.

## 9. Testing requirements added by this decision

Add tests proving:

- unseen paraphrases can be classified correctly by an LLM stub/schema path without production phrase rules
- understanding receives relevant recent/durable context
- composition receives verified SQL/RAG facts and does not invent absent fields
- two users/sessions do not leak history into each other
- customer history is included only after correct customer/session association
- current explicit correction overrides old history
- test-detail questions use SQL catalog facts
- preparation follow-ups can combine selected test context with RAG
- broad category requests produce real options rather than arbitrary LLM selection
- ordinal selection resolves against active `SearchSnapshot`
- no symptom-based test recommendation
- mutation-blocking policy decisions remain deterministic in Phase 4 even when the LLM explains the policy

## 10. Phase boundary

Phase 3 owns:

- LLM understanding
- context loading
- customer-history context interface
- clarification
- routing
- SQL/RAG read paths
- LLM response composition
- validation/persistence

Phase 4 owns authoritative mutation enforcement and business actions.

The system should feel AI-driven conversationally, while deterministic services remain the safety and business-truth boundary.

## 11. Verification Status

- **Status:** **LIVE_VERIFIED**
- **LLM Provider / Model:** Google Gemini (`gemini-2.5-flash`) via `GeminiAgentLLM`.
- **Validation Results:** 100% Safety boundary compliance (no diagnosis, no prescription, no symptom triage), 100% session/customer isolation, 100% ordinal snapshot resolution, and 100% action boundary protection (zero fake confirmations).
- **QA Documentation:** See [docs/qa/phase3_langgraph_qa.md](file:///d:/MediLab/docs/qa/phase3_langgraph_qa.md) and [docs/evaluation/phase3_agent_eval.md](file:///d:/MediLab/docs/evaluation/phase3_agent_eval.md).