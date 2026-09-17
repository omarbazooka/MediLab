"""Signal-based retrieval grading without synthetic confidence scores."""

from __future__ import annotations

from app.rag.types import RetrievalOutcome, RetrievedChunk

# Engineering thresholds calibrated against pgvector cosine distance and Jina v3:
# - Strong topical/monolingual match: <= 0.48
# - Cross-lingual semantic topical match: <= 0.61 (with rank concentration gap >= 0.08)
# - Rank concentration threshold: >= 0.08 difference between 1st and 2nd candidate
# - Noise floor / Unrelated query ceiling: > 0.65
MAX_GOOD_COSINE_DISTANCE = 0.48
MAX_CROSS_LINGUAL_COSINE_DISTANCE = 0.61
MIN_RANK_CONCENTRATION_GAP = 0.08
MAX_PLAUSIBLE_COSINE_DISTANCE = 0.65


def grade_retrieval(
    chunks: list[RetrievedChunk],
    is_ambiguous_query: bool = False,
) -> RetrievalOutcome:
    """Grade retrieval quality using observable, deterministic signals.

    Outcomes:
    - AMBIGUOUS_USER_QUERY: Anaphoric/ambiguous reference could not be resolved.
    - NO_KNOWLEDGE: No candidates found or all candidates fall below relevance floor.
    - GOOD: Strong evidence (dual-arm agreement, direct lexical evidence, or rank concentration).
    - WEAK_RETRY: Plausible but borderline match warranting a bounded query retry.
    """
    if is_ambiguous_query:
        return RetrievalOutcome.AMBIGUOUS_USER_QUERY

    if not chunks:
        return RetrievalOutcome.NO_KNOWLEDGE

    top_chunk = chunks[0]
    top_distance = top_chunk.cosine_distance

    # Measure rank concentration / distance gap between top candidate and runner-up
    rank_concentration_gap = 0.0
    if len(chunks) >= 2 and chunks[1].cosine_distance is not None and top_distance is not None:
        rank_concentration_gap = chunks[1].cosine_distance - top_distance

    # If top chunk distance is beyond plausible threshold (> 0.65) without strong lexical score: NO_KNOWLEDGE
    if top_distance is not None and top_distance > MAX_PLAUSIBLE_COSINE_DISTANCE:
        if top_chunk.lexical_rank is None or (top_chunk.fts_score or 0) <= 0.05:
            return RetrievalOutcome.NO_KNOWLEDGE

    # Signal 1: Strong lexical rank alone (direct keyword match with meaningful FTS score)
    if top_chunk.lexical_rank == 1 and (top_chunk.fts_score or 0) > 0.15:
        return RetrievalOutcome.GOOD

    # Signal 2: Dual-arm agreement with reasonable distance
    has_dual_arm_agreement = (
        top_chunk.semantic_rank is not None and top_chunk.lexical_rank is not None
    )
    if has_dual_arm_agreement and (top_distance is None or top_distance <= 0.50):
        return RetrievalOutcome.GOOD

    # Signal 3: Strong semantic similarity (<= 0.48) with non-zero rank concentration or single chunk
    if top_distance is not None and top_distance <= MAX_GOOD_COSINE_DISTANCE:
        if len(chunks) == 1 or rank_concentration_gap >= 0.04 or top_chunk.lexical_rank is not None:
            return RetrievalOutcome.GOOD

    # Signal 4: Cross-lingual topical match (<= 0.61) backed by strong rank concentration (gap >= 0.08)
    if (
        top_distance is not None
        and top_distance <= MAX_CROSS_LINGUAL_COSINE_DISTANCE
        and rank_concentration_gap >= MIN_RANK_CONCENTRATION_GAP
    ):
        return RetrievalOutcome.GOOD

    # Signal 5: Borderline candidate -> WEAK_RETRY (candidate for single bounded retry)
    if top_distance is not None and top_distance <= MAX_PLAUSIBLE_COSINE_DISTANCE:
        if top_chunk.lexical_rank is not None or rank_concentration_gap >= 0.04:
            return RetrievalOutcome.WEAK_RETRY

    # Signal 6: Distance exceeds plausible threshold or flat noise with no lexical evidence -> NO_KNOWLEDGE
    return RetrievalOutcome.NO_KNOWLEDGE
