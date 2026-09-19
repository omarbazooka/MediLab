"""Deterministic context-aware query rewrite and ambiguity detection."""

from __future__ import annotations

import re
from typing import Any

from app.rag.types import RewriteResult

# Ambiguous pronouns/anaphoric references in English
EN_AMBIGUOUS_PATTERNS = [
    r"\b(it|this|that|them|these|those)\b",
    r"\b(for it|before it|after it|about it|to it|with it)\b",
]

# Ambiguous pronouns/demonstratives and bound clitics in Egyptian/Standard Arabic
AR_AMBIGUOUS_PATTERNS = [
    r"(?:\s|^)(ده|دي|ديه|ذلك|تلك|هذا|هذه|هو|هي)(?:\s|[؟?!.]|$)",
    r"(?:\s|^)(قبله|قبلها|بعده|بعدها|عنه|عنها|له|لها|فيه|فيها|عليه|عليها)(?:\s|[؟?!.]|$)",
    r"(?:\s|^)(ده قبلها|ده بعده|ده قبله)(?:\s|[؟?!.]|$)",
]

COMPILED_EN_PATTERNS = [re.compile(p, re.IGNORECASE) for p in EN_AMBIGUOUS_PATTERNS]
COMPILED_AR_PATTERNS = [re.compile(p, re.IGNORECASE) for p in AR_AMBIGUOUS_PATTERNS]

# Non-anaphoric dummy/expletive idioms where 'it' does not refer to a medical entity
NON_ANAPHORIC_IDIOMS = [
    re.compile(r"\bhow\s+long\s+does\s+it\s+take\b", re.IGNORECASE),
    re.compile(r"\bhow\s+much\s+does\s+it\s+cost\b", re.IGNORECASE),
    re.compile(r"\bis\s+it\s+possible\s+to\b", re.IGNORECASE),
]


def has_ambiguous_reference(query: str) -> bool:
    """Detect whether a query contains unresolved anaphoric references."""
    clean = query.strip()
    # Mask out non-anaphoric dummy idioms before pronoun checking
    for idiom in NON_ANAPHORIC_IDIOMS:
        clean = idiom.sub("", clean)

    for pattern in COMPILED_EN_PATTERNS:
        if pattern.search(clean):
            return True
    for pattern in COMPILED_AR_PATTERNS:
        if pattern.search(clean):
            return True
    return False


def rewrite_query(query: str, context: dict[str, Any] | None = None) -> RewriteResult:
    """Perform deterministic context-aware query rewriting.

    Rules:
    - If the query contains an ambiguous reference without trusted context:
      Returns status="AMBIGUOUS_USER_QUERY" (DO NOT GUESS).
    - If ambiguous reference exists with trusted context (e.g. selected_test_name,
      selected_package_name, current_subject):
      Rewrites query into a standalone search query.
    - If unambiguous, returns original query intact.
    """
    clean_query = query.strip()
    if not clean_query:
        return RewriteResult(
            original_query=query,
            rewritten_query="",
            is_ambiguous=False,
            status="NORMAL",
        )

    is_ambig = has_ambiguous_reference(clean_query)

    # Extract trusted context entities
    trusted_entity: str | None = None
    if context:
        for key in ("selected_test_name", "selected_package_name", "current_subject"):
            val = context.get(key)
            if val and isinstance(val, str) and val.strip():
                trusted_entity = val.strip()
                break

    if is_ambig:
        if not trusted_entity:
            # Ambiguous reference with no contextual grounding: DO NOT GUESS
            return RewriteResult(
                original_query=clean_query,
                rewritten_query=clean_query,
                is_ambiguous=True,
                status="AMBIGUOUS_USER_QUERY",
            )

        # Ground the query with the trusted entity
        # e.g. "Do I need fasting for it?" + "TSH" -> "TSH: Do I need fasting for it?"
        rewritten = f"{trusted_entity} — {clean_query}"
        return RewriteResult(
            original_query=clean_query,
            rewritten_query=rewritten,
            is_ambiguous=False,
            resolved_entity=trusted_entity,
            status="REWRITTEN",
        )

    # Clean standalone query
    return RewriteResult(
        original_query=clean_query,
        rewritten_query=clean_query,
        is_ambiguous=False,
        status="NORMAL",
    )
