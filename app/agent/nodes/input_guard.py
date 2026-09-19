"""Input validation, normalization, and safety guard node."""

from __future__ import annotations

import re
import time
from typing import Any

from app.agent.state import MediLabAgentState

# Session ID pattern: alphanumeric with hyphens, underscores, colons, dots (1-128 chars)
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

# Suspicious prompt injection boundary markers
INJECTION_OVERRIDE_PATTERNS = [
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions"),
    re.compile(r"(?i)show\s+me\s+(?:your\s+)?system\s+prompt"),
    re.compile(r"(?i)<\s*system\s*>"),
    re.compile(r"(?i)\[\s*system\s*\]"),
]

MAX_INPUT_LENGTH = 1000


def input_guard(state: MediLabAgentState) -> dict[str, Any]:
    """Validate, normalize input message, and check orchestration boundary constraints."""
    t_start = time.perf_counter()
    timings = dict(state.get("node_timings", {}))
    errors: list[str] = list(state.get("controlled_errors", []))

    session_id = state.get("session_id", "").strip()
    raw_message = state.get("user_message", "")

    # 1. Validate session_id
    if not session_id or not SESSION_ID_PATTERN.fullmatch(session_id):
        timings["input_guard"] = (time.perf_counter() - t_start) * 1000
        return {
            "is_safe": False,
            "controlled_errors": errors + ["Invalid or missing session_id."],
            "response_goal": "CONTROLLED_ERROR",
            "final_response": "Invalid session identifier. Please start a new session.",
            "node_timings": timings,
        }

    # 2. Reject empty or whitespace-only messages
    normalized = " ".join(raw_message.split())
    if not normalized:
        timings["input_guard"] = (time.perf_counter() - t_start) * 1000
        return {
            "is_safe": False,
            "controlled_errors": errors + ["Empty user message."],
            "response_goal": "CONTROLLED_ERROR",
            "final_response": "Please enter a valid message so I can assist you.",
            "node_timings": timings,
        }

    # 3. Enforce maximum input length
    if len(normalized) > MAX_INPUT_LENGTH:
        timings["input_guard"] = (time.perf_counter() - t_start) * 1000
        return {
            "is_safe": False,
            "controlled_errors": errors
            + [f"Input length {len(normalized)} exceeds maximum {MAX_INPUT_LENGTH}."],
            "response_goal": "CONTROLLED_ERROR",
            "final_response": f"Message is too long. Please shorten your message to under {MAX_INPUT_LENGTH} characters.",
            "node_timings": timings,
        }

    # 4. Prompt injection boundary check (neutralize override attempts)
    sanitized = normalized
    has_injection_marker = False
    for pat in INJECTION_OVERRIDE_PATTERNS:
        if pat.search(sanitized):
            has_injection_marker = True
            sanitized = pat.sub("", sanitized).strip()

    if has_injection_marker:
        errors.append("Potential prompt-injection override marker detected and sanitized.")

    timings["input_guard"] = (time.perf_counter() - t_start) * 1000
    return {
        "normalized_user_message": sanitized or normalized,
        "controlled_errors": errors,
        "node_timings": timings,
    }
