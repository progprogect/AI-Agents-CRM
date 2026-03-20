"""Escalation models."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Built-in "contact info" rule when detect_contact is enabled (prompt + normalization)
BUILTIN_CONTACT_RULE_ID = "__builtin_contact__"


class EscalationType(str, Enum):
    """Type of escalation."""

    URGENT = "urgent"
    MEDICAL = "medical"
    BOOKING = "booking"
    REPEAT_PATIENT = "repeat_patient"
    CUSTOM = "custom"
    NONE = "none"


class ContactInfo(BaseModel):
    """Extracted contact information from message."""

    phone_numbers: list[str] = Field(
        default_factory=list,
        description="List of phone numbers found in message (any format: international, local, with spaces/dashes)"
    )
    emails: list[str] = Field(
        default_factory=list,
        description="List of email addresses found in message"
    )


class EscalationDecision(BaseModel):
    """Escalation decision from LLM."""

    model_config = ConfigDict(use_enum_values=True)

    needs_escalation: bool = Field(..., description="Whether escalation is needed")
    escalation_type: EscalationType = Field(
        default=EscalationType.NONE, description="Type of escalation"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score (0-1)"
    )
    reason: str = Field(..., description="Reason for escalation decision")
    suggested_action: str = Field(
        ..., description="Suggested action to take"
    )
    matched_rule_ids: list[str] = Field(
        default_factory=list,
        description="IDs of escalation rules that matched (exact ids from the rules list in the prompt)",
    )
    extracted_contacts: Optional[ContactInfo] = Field(
        default=None,
        description="Contact information extracted from message (phone numbers, emails)"
    )


FAIL_CLOSED_ESCALATION_REASON = (
    "Escalation check failed; handed off for human review"
)


def fail_closed_escalation_decision() -> EscalationDecision:
    """When the classifier cannot run: escalate so handoff + notifications still occur."""
    return EscalationDecision(
        needs_escalation=True,
        escalation_type=EscalationType.CUSTOM,
        confidence=1.0,
        reason=FAIL_CLOSED_ESCALATION_REASON,
        suggested_action="human_review",
        matched_rule_ids=[],
        extracted_contacts=ContactInfo(),
    )
