"""Strict Pydantic schemas for LLM inputs and structured outputs in MediLab AI."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SafetyCategory(StrEnum):
    """Categorization for clinical safety boundaries."""

    SAFE_OPERATIONAL = "SAFE_OPERATIONAL"
    MEDICAL_ADVICE = "MEDICAL_ADVICE"
    RESULT_INTERPRETATION = "RESULT_INTERPRETATION"
    MEDICATION_ADVICE = "MEDICATION_ADVICE"
    SYMPTOM_BASED_TEST_RECOMMENDATION = "SYMPTOM_BASED_TEST_RECOMMENDATION"
    OTHER_CLINICAL_UNSAFE = "OTHER_CLINICAL_UNSAFE"


class SafetyClassification(BaseModel):
    """Structured output from LLM safety classification."""

    category: SafetyCategory = Field(default=SafetyCategory.SAFE_OPERATIONAL)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str | None = Field(default=None)

    @property
    def is_safe(self) -> bool:
        """Return True if safe for customer-service operational processing."""
        return self.category == SafetyCategory.SAFE_OPERATIONAL


class AgentIntent(StrEnum):
    """Controlled taxonomy of customer-service intents."""

    # Structured catalog & branches
    TEST_SEARCH = "TEST_SEARCH"
    TEST_DETAILS = "TEST_DETAILS"
    TEST_DEFINITION = "TEST_DEFINITION"
    TEST_PRICE = "TEST_PRICE"
    SAMPLE_TYPE = "SAMPLE_TYPE"
    RESULT_TURNAROUND = "RESULT_TURNAROUND"
    PACKAGE_SEARCH = "PACKAGE_SEARCH"
    PACKAGE_DETAILS = "PACKAGE_DETAILS"
    PACKAGE_PRICE = "PACKAGE_PRICE"
    BRANCH_INFO = "BRANCH_INFO"
    AVAILABILITY = "AVAILABILITY"

    # RAG knowledge
    PREPARATION = "PREPARATION"
    POLICY = "POLICY"
    FAQ = "FAQ"
    HOME_SERVICE_INFO = "HOME_SERVICE_INFO"
    CANCELLATION_POLICY = "CANCELLATION_POLICY"

    # Customer history
    CUSTOMER_HISTORY = "CUSTOMER_HISTORY"

    # Action boundaries (Phase 4 interface)
    BOOK_BRANCH_VISIT = "BOOK_BRANCH_VISIT"
    BOOK_HOME_VISIT = "BOOK_HOME_VISIT"
    CHECK_BOOKING = "CHECK_BOOKING"
    CANCEL_BOOKING = "CANCEL_BOOKING"

    # Conversational & general
    GENERAL_CONVERSATION = "GENERAL_CONVERSATION"
    UNKNOWN_AMBIGUOUS = "UNKNOWN_AMBIGUOUS"


class RequestPlan(BaseModel):
    """Structured understanding and execution plan produced by the LLM."""

    primary_intent: AgentIntent = Field(default=AgentIntent.UNKNOWN_AMBIGUOUS)
    requested_information: list[str] = Field(
        default_factory=list,
        description="Specific topics requested, e.g. ['definition', 'price', 'preparation']",
    )
    entities: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted entities such as test_query, package_query, branch_name, ordinal_ref",
    )
    references: list[str] = Field(
        default_factory=list,
        description="Referential terms found in utterance, e.g. ['it', 'the second one', 'ده']",
    )
    ambiguities: list[str] = Field(
        default_factory=list,
        description="Identified ambiguities or missing entity identifiers",
    )
    requires_structured_data: bool = Field(default=False)
    requires_rag: bool = Field(default=False)
    requires_customer_history: bool = Field(default=False)
    action_intent: str | None = Field(default=None)
    needs_clarification: bool = Field(default=False)
    clarification_target: str | None = Field(default=None)
    language: str = Field(
        default="en",
        description="User language: 'ar', 'en', or 'mixed'",
    )


class ResponseGoal(StrEnum):
    """High-level goal for the final composed response."""

    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    SAFE_BOUNDARY = "SAFE_BOUNDARY"
    NO_KNOWLEDGE = "NO_KNOWLEDGE"
    CONTROLLED_ERROR = "CONTROLLED_ERROR"
    ACTION_NOT_YET_EXECUTABLE = "ACTION_NOT_YET_EXECUTABLE"


class ResponseDraft(BaseModel):
    """Draft response produced by LLM composer."""

    text: str = Field(min_length=1)
    response_goal: ResponseGoal = Field(default=ResponseGoal.ANSWER)


class ValidationOutcome(BaseModel):
    """Outcome of response validation check."""

    is_valid: bool = Field(default=True)
    reasons: list[str] = Field(default_factory=list)
    repaired_text: str | None = Field(default=None)
