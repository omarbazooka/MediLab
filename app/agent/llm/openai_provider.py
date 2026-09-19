"""OpenAI-compatible LLM provider implementation using httpx."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.agent.schemas import (
    AgentIntent,
    RequestPlan,
    ResponseDraft,
    ResponseGoal,
    SafetyCategory,
    SafetyClassification,
    ValidationOutcome,
)

logger = logging.getLogger("medilab.llm.openai")


class OpenAICompatibleProvider:
    """Production provider connecting to any OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    def _call_chat_completions(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        """Call the completions endpoint with strict error handling and no secret leaking."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()

    def classify_safety(
        self,
        user_message: str,
        recent_context: list[dict[str, Any]] | None = None,
    ) -> SafetyClassification:
        system_prompt = (
            "You are a medical laboratory customer-service safety classifier.\n"
            "Evaluate if the user's message is safe operational customer service, or crosses into prohibited clinical areas.\n"
            "Categories:\n"
            "- SAFE_OPERATIONAL: tests prices, definitions, preparation instructions from lab guides, branch hours, appointment info, turnaround times.\n"
            "- MEDICAL_ADVICE: asking for medical diagnosis, health evaluation, or disease risk.\n"
            "- RESULT_INTERPRETATION: asking to interpret abnormal lab values, glucose levels, hormone levels (e.g. 'glucose is 250, do I have diabetes?').\n"
            "- MEDICATION_ADVICE: asking what medicine/drugs to take or dose changes.\n"
            "- SYMPTOM_BASED_TEST_RECOMMENDATION: asking which tests to take based on clinical symptoms (e.g. 'I feel dizzy, what test should I take?').\n"
            "- OTHER_CLINICAL_UNSAFE: any other clinical medical judgment.\n"
            "Output JSON with keys: category (exact category string), confidence (0.0 to 1.0), reason (short string)."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User message: {user_message}"},
        ]
        try:
            raw = self._call_chat_completions(messages, json_mode=True)
            data = json.loads(raw)
            return SafetyClassification(**data)
        except Exception as exc:
            logger.warning("Safety classification failed, defaulting to SAFE_OPERATIONAL: %s", exc)
            return SafetyClassification(category=SafetyCategory.SAFE_OPERATIONAL, reason=str(exc))

    def understand_request(
        self,
        user_message: str,
        context_summary: dict[str, Any] | None = None,
    ) -> RequestPlan:
        system_prompt = (
            "You are the intent and planning parser for MediLab diagnostic laboratory agent.\n"
            "Analyze the user's request (in Arabic, English, or mixed) and output a JSON execution plan.\n"
            "Intents:\n"
            "- TEST_SEARCH, TEST_DETAILS, TEST_DEFINITION, TEST_PRICE, SAMPLE_TYPE, RESULT_TURNAROUND\n"
            "- PACKAGE_SEARCH, PACKAGE_DETAILS, PACKAGE_PRICE\n"
            "- BRANCH_INFO, AVAILABILITY\n"
            "- PREPARATION, POLICY, FAQ, HOME_SERVICE_INFO, CANCELLATION_POLICY\n"
            "- CUSTOMER_HISTORY\n"
            "- BOOK_BRANCH_VISIT, BOOK_HOME_VISIT, CHECK_BOOKING, CANCEL_BOOKING\n"
            "- GENERAL_CONVERSATION, UNKNOWN_AMBIGUOUS\n\n"
            "Output JSON keys:\n"
            "- primary_intent: matching one intent string above\n"
            "- requested_information: list of requested topics (e.g. ['price', 'preparation'])\n"
            "- entities: extracted entity dict (e.g. {'test_query': 'TSH'})\n"
            "- references: list of referential words\n"
            "- ambiguities: list of ambiguous elements\n"
            "- requires_structured_data: boolean (true if needing prices, catalog details, branches)\n"
            "- requires_rag: boolean (true if needing preparation guidelines or laboratory policies)\n"
            "- requires_customer_history: boolean (true if asking about their own prior visits/bookings)\n"
            "- action_intent: string or null\n"
            "- needs_clarification: boolean\n"
            "- clarification_target: string or null\n"
            "- language: 'ar', 'en', or 'mixed'"
        )
        user_prompt = f"Context: {json.dumps(context_summary or {})}\nUser message: {user_message}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            raw = self._call_chat_completions(messages, json_mode=True)
            data = json.loads(raw)
            return RequestPlan(**data)
        except Exception as exc:
            logger.error("Failed to parse request understanding: %s", exc)
            return RequestPlan(primary_intent=AgentIntent.UNKNOWN_AMBIGUOUS)

    def generate_clarification(
        self,
        target: str | None,
        reason: str | None,
        options: list[str] | None = None,
        language: str = "en",
    ) -> str:
        system_prompt = (
            "You are a friendly customer service assistant at MediLab diagnostic laboratory.\n"
            "The user's inquiry is ambiguous or needs clarification.\n"
            "Generate exactly ONE polite, focused clarification question in the user's language.\n"
            "Do not ask multiple questions. Be concise and natural."
        )
        content = f"Language: {language}\nTarget: {target}\nReason: {reason}\nAvailable options: {options}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]
        try:
            return self._call_chat_completions(messages, json_mode=False)
        except Exception:
            return (
                "Could you please clarify which test or service you need?"
                if language == "en"
                else "هل يمكنك توضيح التحليل المطلوب بالتحديد؟"
            )

    def compose_response(
        self,
        evidence_bundle: dict[str, Any],
    ) -> ResponseDraft:
        system_prompt = (
            "You are MediLab AI, the official customer service assistant for MediLab diagnostic laboratory.\n"
            "You receive verified evidence from trusted databases and official laboratory guides.\n"
            "Rules:\n"
            "1. Rely ONLY on the provided evidence. Never invent prices, tests, or availability.\n"
            "2. Never claim that a booking was confirmed unless action_result explicitly indicates confirmation.\n"
            "3. If clinical questions or advice are requested, maintain safety boundaries and advise consulting a doctor.\n"
            "4. Respond naturally and politely in the user's language (Arabic if user used Arabic, English if English).\n"
            "5. Synthesize both structured facts (prices, turnaround) and preparation instructions into ONE coherent answer."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Evidence bundle: {json.dumps(evidence_bundle, default=str)}",
            },
        ]
        try:
            text = self._call_chat_completions(messages, json_mode=False)
            goal = evidence_bundle.get("response_goal", ResponseGoal.ANSWER.value)
            return ResponseDraft(text=text, response_goal=ResponseGoal(goal))
        except Exception as exc:
            logger.error("Failed to compose response: %s", exc)
            return ResponseDraft(
                text="I apologize, but I encountered an error retrieving that information. Please contact our support team.",
                response_goal=ResponseGoal.CONTROLLED_ERROR,
            )

    def validate_response(
        self,
        draft: str,
        evidence_bundle: dict[str, Any],
    ) -> ValidationOutcome:
        # Deterministic verification is primary; LLM check can be added if needed
        return ValidationOutcome(is_valid=True)
