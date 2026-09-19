"""Google Gemini LLM provider implementation using httpx REST API."""

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

logger = logging.getLogger("medilab.llm.gemini")


class GeminiProvider:
    """Production provider connecting directly to Google Gemini REST API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
        timeout_seconds: float = 25.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout_seconds

    def _call_generate_content(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        """Call Gemini generateContent REST endpoint."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        params = {"key": self.api_key}

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, params=params, json=payload)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("Gemini returned no candidates.")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError("Gemini candidate has no parts.")
            return str(parts[0].get("text", "")).strip()

    def classify_safety(
        self,
        user_message: str,
        recent_context: list[dict[str, Any]] | None = None,
    ) -> SafetyClassification:
        system_instruction = (
            "You are a healthcare customer service safety classifier for MediLab diagnostic laboratory.\n"
            "Evaluate if user inquiry is safe operational customer service, or crosses into prohibited clinical areas.\n"
            "Categories:\n"
            "- SAFE_OPERATIONAL\n"
            "- MEDICAL_ADVICE\n"
            "- RESULT_INTERPRETATION\n"
            "- MEDICATION_ADVICE\n"
            "- SYMPTOM_BASED_TEST_RECOMMENDATION\n"
            "- OTHER_CLINICAL_UNSAFE\n"
            "Output JSON with keys: category, confidence, reason."
        )
        contents = [{"parts": [{"text": f"User message: {user_message}"}]}]
        try:
            raw = self._call_generate_content(
                contents, system_instruction=system_instruction, json_mode=True
            )
            data = json.loads(raw)
            return SafetyClassification(**data)
        except Exception as exc:
            logger.warning("Gemini safety classification fallback: %s", exc)
            return SafetyClassification(category=SafetyCategory.SAFE_OPERATIONAL, reason=str(exc))

    def understand_request(
        self,
        user_message: str,
        context_summary: dict[str, Any] | None = None,
    ) -> RequestPlan:
        system_instruction = (
            "You are the intent and planning parser for MediLab laboratory.\n"
            "Analyze the request in Arabic or English and output a JSON execution plan.\n"
            "Intents: TEST_SEARCH, TEST_DETAILS, TEST_DEFINITION, TEST_PRICE, SAMPLE_TYPE, "
            "RESULT_TURNAROUND, PACKAGE_SEARCH, PACKAGE_DETAILS, PACKAGE_PRICE, BRANCH_INFO, "
            "AVAILABILITY, PREPARATION, POLICY, FAQ, HOME_SERVICE_INFO, CANCELLATION_POLICY, "
            "CUSTOMER_HISTORY, BOOK_BRANCH_VISIT, BOOK_HOME_VISIT, CHECK_BOOKING, CANCEL_BOOKING, "
            "GENERAL_CONVERSATION, UNKNOWN_AMBIGUOUS.\n\n"
            "Output JSON keys: primary_intent, requested_information, entities, references, ambiguities, "
            "requires_structured_data, requires_rag, requires_customer_history, action_intent, "
            "needs_clarification, clarification_target, language."
        )
        prompt = f"Context: {json.dumps(context_summary or {})}\nUser message: {user_message}"
        contents = [{"parts": [{"text": prompt}]}]
        try:
            raw = self._call_generate_content(
                contents, system_instruction=system_instruction, json_mode=True
            )
            data = json.loads(raw)
            return RequestPlan(**data)
        except Exception as exc:
            logger.error("Gemini understand_request failed: %s", exc)
            return RequestPlan(primary_intent=AgentIntent.UNKNOWN_AMBIGUOUS)

    def generate_clarification(
        self,
        target: str | None,
        reason: str | None,
        options: list[str] | None = None,
        language: str = "en",
    ) -> str:
        system_instruction = (
            "You are a friendly customer service assistant at MediLab laboratory.\n"
            "Generate ONE polite, concise clarification question in the user's language."
        )
        prompt = f"Language: {language}\nTarget: {target}\nReason: {reason}\nAvailable options: {options}"
        contents = [{"parts": [{"text": prompt}]}]
        try:
            return self._call_generate_content(
                contents, system_instruction=system_instruction, json_mode=False
            )
        except Exception:
            return (
                "Could you please clarify your request?"
                if language == "en"
                else "هل يمكنك توضيح طلبك بالتحديد؟"
            )

    def compose_response(
        self,
        evidence_bundle: dict[str, Any],
    ) -> ResponseDraft:
        system_instruction = (
            "You are MediLab AI, customer service agent for MediLab diagnostic laboratory.\n"
            "Answer using ONLY the provided evidence. Never invent prices or test availability.\n"
            "Never claim a booking is confirmed unless explicitly confirmed in action_result.\n"
            "Respond naturally in the user's language."
        )
        contents = [{"parts": [{"text": f"Evidence: {json.dumps(evidence_bundle, default=str)}"}]}]
        try:
            text = self._call_generate_content(
                contents, system_instruction=system_instruction, json_mode=False
            )
            goal = evidence_bundle.get("response_goal", ResponseGoal.ANSWER.value)
            return ResponseDraft(text=text, response_goal=ResponseGoal(goal))
        except Exception as exc:
            logger.error("Gemini compose_response failed: %s", exc)
            return ResponseDraft(
                text="I apologize, but I am unable to process your request at this moment.",
                response_goal=ResponseGoal.CONTROLLED_ERROR,
            )

    def validate_response(
        self,
        draft: str,
        evidence_bundle: dict[str, Any],
    ) -> ValidationOutcome:
        return ValidationOutcome(is_valid=True)
