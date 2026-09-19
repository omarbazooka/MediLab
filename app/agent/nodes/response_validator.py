"""Response validation node ensuring strict adherence to ground truth and safety boundaries."""

from __future__ import annotations

import re
import time
from typing import Any

from app.agent.state import MediLabAgentState


def response_validator(state: MediLabAgentState) -> dict[str, Any]:
    """Validate that draft response contains no hallucinations, fake actions, or safety breaches."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    draft = (state.get("response_draft") or state.get("final_response") or "").strip()
    language = state.get("language", "en")
    is_valid = True
    reasons: list[str] = []
    repaired_text: str | None = None

    # 1. Non-empty check
    if not draft:
        is_valid = False
        reasons.append("Draft response is empty.")
        repaired_text = (
            "عذراً، لم أتمكن من معالجة طلبك حالياً. يرجى إعادة المحاولة."
            if language == "ar"
            else "I apologize, but I was unable to process your request. Please try again."
        )

    # 2. Fake booking / action success check
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

    # 3. Clinical diagnosis / medical prescription check
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

    # 4. Price hallucination check:
    # If draft mentions EGP / جنيه with an amount, verify the amount is in structured_result
    structured = state.get("structured_result") or {}
    price_matches = re.findall(r"(\d+(?:\.\d{1,2})?)\s*(?:EGP|جنيه|LE)", draft, re.IGNORECASE)
    if price_matches and structured:
        known_prices = set()
        if "test" in structured:
            raw_p = structured["test"].get("price", "")
            nums = re.findall(r"\d+(?:\.\d{1,2})?", raw_p)
            known_prices.update(nums)
        if "package" in structured:
            raw_p = structured["package"].get("price", "")
            nums = re.findall(r"\d+(?:\.\d{1,2})?", raw_p)
            known_prices.update(nums)

        for p_str in price_matches:
            # Check integer or decimal equivalence
            float_val = float(p_str)
            if not any(abs(float(kp) - float_val) < 0.01 for kp in known_prices if kp):
                # If price is mentioned but not in evidence, flag warning
                reasons.append(f"Price {p_str} not verified in structured facts.")

    # 5. NO_KNOWLEDGE check:
    rag_res = state.get("rag_result") or {}
    if rag_res.get("outcome") == "NO_KNOWLEDGE" and state.get("response_goal") == "NO_KNOWLEDGE":
        # Ensure we don't present an ungrounded preparation assertion
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
