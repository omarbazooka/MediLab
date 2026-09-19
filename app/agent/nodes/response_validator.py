"""Response validation node ensuring strict adherence to ground truth and safety boundaries."""

from __future__ import annotations

import re
import time
from typing import Any

from app.agent.state import MediLabAgentState

_PRICE_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?")
_PRICE_MENTION_RE = re.compile(
    r"(\d[\d,]*(?:\.\d{1,2})?)\s*(?:EGP|جنيه|LE)\b",
    re.IGNORECASE,
)


def _collect_verified_prices(value: Any, key_hint: str = "") -> set[float]:
    """Recursively collect numeric values from structured fields explicitly representing prices."""
    prices: set[float] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            child_key = str(key).lower()
            if "price" in child_key and isinstance(child, (str, int, float)):
                for match in _PRICE_NUMBER_RE.findall(str(child)):
                    try:
                        prices.add(float(match.replace(",", "")))
                    except ValueError:
                        continue
            prices.update(_collect_verified_prices(child, child_key))
    elif isinstance(value, list):
        for child in value:
            prices.update(_collect_verified_prices(child, key_hint))
    return prices


def _has_committed_action_success(action_result: Any) -> bool:
    """Return True only for an explicit successful committed mutation result."""
    return bool(
        isinstance(action_result, dict)
        and action_result.get("success") is True
        and action_result.get("committed") is True
    )


def response_validator(state: MediLabAgentState) -> dict[str, Any]:
    """Validate that draft response contains no hallucinations, fake actions, or safety breaches."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    draft = (state.get("response_draft") or state.get("final_response") or "").strip()
    language = state.get("language", "en")
    is_valid = True
    reasons: list[str] = []
    repaired_text: str | None = None

    if not draft:
        is_valid = False
        reasons.append("Draft response is empty.")
        repaired_text = (
            "عذراً، لم أتمكن من معالجة طلبك حالياً. يرجى إعادة المحاولة."
            if language == "ar"
            else "I apologize, but I was unable to process your request. Please try again."
        )

    lower_draft = draft.lower()
    has_action_success_claim = any(
        phrase in lower_draft
        for phrase in [
            "your booking is confirmed",
            "your booking has been confirmed",
            "your appointment is confirmed",
            "your appointment has been confirmed",
            "we have booked your",
            "booking has been cancelled successfully",
            "booking was cancelled successfully",
            "تم تأكيد حجزك",
            "تم الحجز بنجاح",
            "حجزك مؤكد",
            "لقد تم حجز موعدك",
            "تم إلغاء الحجز بنجاح",
        ]
    )
    if has_action_success_claim and not _has_committed_action_success(state.get("action_result")):
        is_valid = False
        reasons.append(
            "Draft falsely claims action success without an explicit committed success result."
        )
        repaired_text = (
            "لا أستطيع تأكيد تنفيذ هذا الإجراء من دون نتيجة ناجحة وموثقة من نظام الحجوزات."
            if language == "ar"
            else "I cannot confirm that action without a verified successful result from the booking system."
        )

    has_medical_diagnosis_claim = any(
        phrase in lower_draft
        for phrase in [
            "you have diabetes",
            "diagnosed with",
            "أنت مصاب بالسكري",
            "تشخيصك هو",
            "أنصحك بتناول دواء",
            "take this medicine",
        ]
    )
    if has_medical_diagnosis_claim:
        is_valid = False
        reasons.append("Draft contains prohibited medical diagnosis or medication prescription.")
        repaired_text = (
            "في مختبرات ميدي لاب نقدم خدمات الفحوصات الطبية، ولا نقدم تشخيصاً طبياً أو وصفات علاجية. يرجى استشارة مختص رعاية صحية مؤهل."
            if language == "ar"
            else "MediLab provides diagnostic laboratory services. We do not provide clinical diagnoses or prescriptions. Please consult a qualified healthcare professional."
        )

    # MediLab is not an emergency-triage service. Even an LLM/test-double safety
    # response must not tell a customer where to go, whom to call, or how urgently
    # to seek emergency care. Keep the boundary informational and direct medical
    # decisions to a qualified healthcare professional instead.
    has_emergency_triage_guidance = any(
        phrase in lower_draft
        for phrase in [
            "seek immediate emergency care",
            "go to the emergency room",
            "go to the nearest hospital",
            "nearest hospital",
            "call emergency services",
            "call an ambulance",
            "اذهب إلى الطوارئ",
            "توجه إلى الطوارئ",
            "أقرب مستشفى",
            "اتصل بالإسعاف",
        ]
    )
    if has_emergency_triage_guidance:
        is_valid = False
        reasons.append("Draft contains prohibited emergency-triage guidance.")
        repaired_text = (
            "لا يمكن لميدي لاب تقديم إرشادات فرز أو توجيه للطوارئ. يرجى الرجوع إلى مختص رعاية صحية مؤهل بشأن القرارات الطبية."
            if language == "ar"
            else "MediLab cannot provide immediate emergency or hospital triage guidance. Please consult a qualified healthcare professional regarding medical decisions."
        )

    price_mentions = _PRICE_MENTION_RE.findall(draft)
    if price_mentions:
        structured = state.get("structured_result") or {}
        known_prices = _collect_verified_prices(structured)
        unverified: list[str] = []
        for raw_price in price_mentions:
            mentioned = float(raw_price.replace(",", ""))
            if not any(abs(known - mentioned) < 0.01 for known in known_prices):
                unverified.append(raw_price)

        if unverified:
            is_valid = False
            reasons.append(
                "Response contains price amount(s) not present in verified structured facts: "
                + ", ".join(unverified)
            )
            repaired_text = (
                "لا أستطيع تأكيد السعر من البيانات الموثقة المتاحة في هذه المحادثة. يمكنني إعادة البحث في بيانات ميدي لاب الحالية للتحقق من السعر."
                if language == "ar"
                else "I cannot verify that price from the trusted structured data available for this turn. I can re-check MediLab's current catalog data before quoting a price."
            )

    rag_res = state.get("rag_result") or {}
    if rag_res.get("outcome") == "NO_KNOWLEDGE" and state.get("response_goal") == "NO_KNOWLEDGE":
        if any(w in lower_draft for w in ["fast for", "requires fasting", "يجب الصيام"]):
            is_valid = False
            reasons.append(
                "Draft asserts specific fasting requirement despite NO_KNOWLEDGE outcome."
            )
            repaired_text = (
                "لم أجد تعليمات تحضير خاصة بهذا الفحص في دليل الإرشادات الحالي. يرجى مراجعة فريق ميدي لاب للتأكيد."
                if language == "ar"
                else "I could not find specific preparation guidance for this test in the current approved knowledge base. Please check with MediLab staff for confirmation."
            )

    final_text = repaired_text if (not is_valid and repaired_text) else draft

    timings["response_validator"] = (time.perf_counter() - t_start) * 1000

    return {
        "final_response": final_text,
        "validation_result": {
            "is_valid": is_valid,
            "reasons": reasons,
            "repaired": bool(repaired_text),
        },
        "node_timings": timings,
    }
