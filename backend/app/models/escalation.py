"""Escalation models."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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
    extracted_contacts: Optional[ContactInfo] = Field(
        default=None,
        description="Contact information extracted from message (phone numbers, emails)"
    )

    class Config:
        """Pydantic config."""

        use_enum_values = True

