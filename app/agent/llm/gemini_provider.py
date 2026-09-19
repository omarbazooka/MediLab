"""Google Gemini LLM provider implementation using httpx REST API."""

from __future__ import annotations

import json
import logging
import re
import time
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
        model: str = "gemini-2.5-flash",
        timeout_seconds: float = 30.0,
        temperature: float = 0.0,
        max_retries: int = 1,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required and cannot be empty.")
        self.api_key = api_key
        self.model = model or "gemini-2.5-flash"
        self.timeout = timeout_seconds
        self.temperature = temperature
        self.max_retries = max(0, max_retries)

    def _sanitize_error_text(self, text: str) -> str:
        """Strip API keys and sensitive query params from exception or log messages."""
        if not text:
            return ""
        sanitized = text
        if self.api_key:
            sanitized = sanitized.replace(self.api_key, "[REDACTED_GEMINI_KEY]")
        sanitized = re.sub(r"key=[a-zA-Z0-9_\-]+", "key=[REDACTED]", sanitized)
        sanitized = re.sub(r"key%3D[a-zA-Z0-9_\-]+", "key=[REDACTED]", sanitized)
        return sanitized

    def _call_generate_content(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        """Call Gemini generateContent REST endpoint with bounded retries and sanitized errors."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        params = {"key": self.api_key}

        eff_temp = self.temperature if temperature is None else temperature
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": eff_temp,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self.max_retries:
            try:
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
            except Exception as exc:
                sanitized_msg = self._sanitize_error_text(str(exc))
                logger.warning("Gemini attempt %d failed: %s", attempt + 1, sanitized_msg)
                last_exc = RuntimeError(f"Gemini API call failed: {sanitized_msg}")
                attempt += 1
                if attempt <= self.max_retries:
                    time.sleep(0.5)

        raise last_exc or RuntimeError("Gemini generateContent call failed.")

    def classify_safety(
        self,
        user_message: str,
        recent_context: list[dict[str, Any]] | None = None,
    ) -> SafetyClassification:
        """Classify user request for medical safety boundaries. Fails closed on any error."""
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
                contents, system_instruction=system_instruction, json_mode=True, temperature=0.0
            )
            data = json.loads(raw)
            return SafetyClassification(**data)
        except Exception as exc:
            sanitized = self._sanitize_error_text(str(exc))
            logger.error("Gemini safety classification failed: %s", sanitized)
            return SafetyClassification(
                category=SafetyCategory.OTHER_CLINICAL_UNSAFE,
                confidence=0.0,
                reason=f"Safety classification unavailable ({sanitized}); failing closed.",
            )

    def understand_request(
        self,
        user_message: str,
        context_summary: dict[str, Any] | None = None,
    ) -> RequestPlan:
        """Parse natural language request into a validated RequestPlan."""
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
                contents, system_instruction=system_instruction, json_mode=True, temperature=0.0
            )
            data = json.loads(raw)
            return RequestPlan(**data)
        except Exception as exc:
            sanitized = self._sanitize_error_text(str(exc))
            logger.error("Gemini understand_request failed: %s", sanitized)
            return RequestPlan(
                primary_intent=AgentIntent.UNKNOWN_AMBIGUOUS, ambiguities=[sanitized]
            )

    def generate_clarification(
        self,
        target: str | None,
        reason: str | None,
        options: list[str] | None = None,
        language: str = "en",
    ) -> str:
        """Generate one contextual clarification question in the user's language."""
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
        """Synthesize natural response strictly using verified evidence."""
        goal = evidence_bundle.get("response_goal", ResponseGoal.ANSWER.value)
        system_instruction = (
            "You are MediLab AI, customer service agent for MediLab diagnostic laboratory.\n"
            "Answer using ONLY the provided evidence. Never invent prices or test availability.\n"
            "Never claim a booking is confirmed unless explicitly confirmed in action_result.\n"
            "If response_goal is SAFE_BOUNDARY, explain politely that MediLab provides diagnostic laboratory "
            "testing and cannot diagnose conditions, interpret laboratory results clinically, or prescribe medications. "
            "Advise the customer to consult a qualified physician or healthcare professional.\n"
            "Respond naturally in the user's language (Arabic if Arabic inquiry, English if English inquiry)."
        )
        contents = [{"parts": [{"text": f"Evidence: {json.dumps(evidence_bundle, default=str)}"}]}]
        try:
            text = self._call_generate_content(
                contents, system_instruction=system_instruction, json_mode=False
            )
            return ResponseDraft(text=text, response_goal=ResponseGoal(goal))
        except Exception as exc:
            sanitized = self._sanitize_error_text(str(exc))
            logger.error("Gemini compose_response failed: %s", sanitized)
            lang = evidence_bundle.get("language", "en")
            fallback_text = (
                "عذراً، لا يمكننا معالجة طلبك حالياً. يرجى المحاولة مرة أخرى أو التواصل مع خدمة عملاء ميدي لاب."
                if lang == "ar"
                else "I apologize, but I am unable to process your request at this moment. Please try again or contact MediLab customer service."
            )
            return ResponseDraft(
                text=fallback_text,
                response_goal=ResponseGoal.CONTROLLED_ERROR,
            )

    def validate_response(
        self,
        draft: str,
        evidence_bundle: dict[str, Any],
    ) -> ValidationOutcome:
        """Deterministic validation is authoritative in response_validator node."""
        return ValidationOutcome(is_valid=True)
