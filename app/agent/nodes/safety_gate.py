"""Healthcare safety gate node evaluating operational vs. clinical boundaries."""

from __future__ import annotations

import time
from typing import Any

from app.agent.llm.factory import get_llm_provider
from app.agent.schemas import SafetyCategory
from app.agent.state import MediLabAgentState


def safety_gate(state: MediLabAgentState) -> dict[str, Any]:
    """Classify user request for medical diagnosis, treatment, or symptom prescribing."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))

    # If already in controlled error from input guard, skip
    if not state.get("is_safe", True) and state.get("response_goal") == "CONTROLLED_ERROR":
        timings["safety_gate"] = (time.perf_counter() - t_start) * 1000
        return {"node_timings": timings}

    user_msg = state.get("normalized_user_message") or state.get("user_message", "")
    recent_msgs = state.get("recent_messages", [])

    provider = get_llm_provider()
    classification = provider.classify_safety(user_message=user_msg, recent_context=recent_msgs)

    # Deterministic secondary fail-safe for critical medical terms
    is_safe = classification.is_safe
    category = classification.category
    reason = classification.reason

    lower = user_msg.lower()
    if is_safe:
        # Check for symptom-based prescribing or result interpretation triggers
        if any(w in lower for w in ["دوخة", "dizziness", "dizzy", "حاسس بدوخة"]) and any(
            w in lower for w in ["تحليل", "test", "أعمل", "إيه", "what"]
        ):
            is_safe = False
            category = SafetyCategory.SYMPTOM_BASED_TEST_RECOMMENDATION
            reason = (
                "Deterministic fail-safe: symptom-based diagnostic test recommendation requested."
            )
        elif ("250" in lower and any(w in lower for w in ["سكر", "glucose", "diabetes"])) or any(
            w in lower for w in ["do i have diabetes", "عندي سكر؟", "interpret my result"]
        ):
            is_safe = False
            category = SafetyCategory.RESULT_INTERPRETATION
            reason = "Deterministic fail-safe: clinical laboratory result interpretation requested."

    timings["safety_gate"] = (time.perf_counter() - t_start) * 1000

    result: dict[str, Any] = {
        "safety_classification": {
            "category": category.value if hasattr(category, "value") else str(category),
            "confidence": classification.confidence,
            "reason": reason,
        },
        "is_safe": is_safe,
        "safety_reason": reason,
        "node_timings": timings,
    }

    if not is_safe:
        result["response_goal"] = "SAFE_BOUNDARY"

    return result
