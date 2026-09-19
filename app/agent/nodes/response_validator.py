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


def response_validator(state: MediLabAgentState) -> dict[str, Any]:
    """Validate that draft response contains no hallucinations, fake actions, or safety breaches."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    draft = (state.get("response_draft") or state.get("final_response") or "").strip()
    language = state.get("language", "en")
    is_valid = True
    reasons: list[str] = []
    repaired_text: str | None = None

    # 1. Non-empty check.
    if not draft:
        is_valid = False
        reasons.append("Draft response is empty.")
        repaired_text = (
            "عذراً، لم أتمكن من معالجة طلبك حالياً. يرجى إعادة المحاولة."
            if language == "ar"
            else "I apologize, but I was unable to process your request. Please try again."
        )

    # 2. Fake booking / action success check.
    lower_draft = draft.lower()
    has_action_success_claim = any(
        phrase in lower_draft
        for phrase in [
            "your booking is confirmed",
            "your booking has been confirmed",
            "your appointment is confirmed",
            "your appointment has been confirmed",
            "we have booked your",
            "تم تأكيد حجزك",
            "تم الحجز بنجاح",
            "حجزك مؤكد",
            "لقد تم حجز موعدك",
        ]
    )
    if has_action_success_claim and not state.get("action_result"):
        is_valid = False
        reasons.append("Draft falsely claims booking confirmation without committed action result.")
        repaired_text = (
            "يمكننا تزويدك بتفاصيل الفحوصات والأسعار والفروع، ولكن الحجز الآلي المباشر غير مفعل حالياً. يرجى التواصل مع خدمة العملاء."
            if language == "ar"
            else "I can provide test details, prices, and branch hours, but direct automated booking is not currently active. Please contact customer service."
        )

    # 3. Clinical diagnosis / medical prescription check.
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
            "في مختبرات ميدي لاب نقدم خدمات الفحوصات الطبية، ولا نقدم تشخيصاً طبياً أو وصفات علاجية. يرجى استشارة طبيب مختص."
            if language == "ar"
            else "MediLab provides diagnostic laboratory services. We do not provide clinical diagnoses or prescriptions. Please consult a doctor."
        )

    # 4. Price grounding check. Any customer-facing currency amount must be backed by
    # structured SQL evidence. Prices are SQL-owned business facts, never RAG/LLM-owned facts.
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

    # 5. NO_KNOWLEDGE check.
    rag_res = state.get("rag_result") or {}
    if rag_res.get("outcome") == "NO_KNOWLEDGE" and state.get("response_goal") == "NO_KNOWLEDGE":
        if any(w in lower_draft for w in ["fast for", "requires fasting", "يجب الصيام"]):
            is_valid = False
            reasons.append(
                "Draft asserts specific fasting requirement despite NO_KNOWLEDGE outcome."
            )
            repaired_text = (
                "لم أجد تعليمات تحضير خاصة بهذا الفحص في دليل الإرشادات الحالي. يرجى مراجعة الفرع للتأكيد."
                if language == "ar"
                else "I could not find specific preparation guidelines for this test in our knowledge base. Please consult our branch staff."
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
