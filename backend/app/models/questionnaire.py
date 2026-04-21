"""Questionnaire feature models.

Templates live per-agent; submissions + responses form an append-only history so
any edit of a value keeps previous answers visible in the admin UI and in audit.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


FIELD_KEY_MAX_LEN = 30  # keep callback_data under Telegram's 64-byte limit
FIELDS_MAX_COUNT = 20
QUICK_REPLIES_MAX = 8
QUICK_REPLY_MAX_LEN = 40


_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,29}$")


class SubmissionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SubmissionSource(str, Enum):
    FILL = "fill"
    EDIT = "edit"


class QuestionnaireField(BaseModel):
    """Single user-facing field in a questionnaire template."""

    key: str = Field(
        ...,
        description=(
            "Stable machine identifier for the field (lowercase, digits, underscore; "
            "must start with a letter). Used as a column-like key and inside Telegram "
            "inline-button callback_data, so limited to 30 chars."
        ),
    )
    label: str = Field(..., min_length=1, max_length=80, description="Short label shown in admin UI")
    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Prompt shown to the user in chat when this field is asked",
    )
    required: bool = Field(default=False, description="If True, user cannot skip this field")
    quick_replies: list[str] = Field(
        default_factory=list,
        description="Optional preset answers rendered as inline buttons (max 8)",
    )
    order: int = Field(default=0, ge=0, description="Sort order inside the questionnaire")

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        if not _FIELD_KEY_RE.match(v):
            raise ValueError(
                "field key must match ^[a-z][a-z0-9_]{0,29}$ "
                "(letters, digits, underscore, start with letter)"
            )
        return v

    @field_validator("quick_replies")
    @classmethod
    def _validate_quick_replies(cls, v: list[str]) -> list[str]:
        if len(v) > QUICK_REPLIES_MAX:
            raise ValueError(f"at most {QUICK_REPLIES_MAX} quick replies per field")
        cleaned: list[str] = []
        for item in v:
            trimmed = (item or "").strip()
            if not trimmed:
                continue
            if len(trimmed) > QUICK_REPLY_MAX_LEN:
                raise ValueError(f"quick reply too long (>{QUICK_REPLY_MAX_LEN} chars)")
            cleaned.append(trimmed)
        return cleaned


class QuestionnaireTemplate(BaseModel):
    """Per-agent questionnaire schema stored in `questionnaire_templates`."""

    agent_id: str
    welcome_message: str = Field(
        default="",
        max_length=2000,
        description="Greeting shown when the user opens the questionnaire",
    )
    completion_message: str = Field(
        default="",
        max_length=2000,
        description="Message shown when the user finishes filling the questionnaire",
    )
    fields: list[QuestionnaireField] = Field(default_factory=list)
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _check_unique_and_size(self) -> "QuestionnaireTemplate":
        if len(self.fields) > FIELDS_MAX_COUNT:
            raise ValueError(f"at most {FIELDS_MAX_COUNT} fields per questionnaire")
        seen: set[str] = set()
        for f in self.fields:
            if f.key in seen:
                raise ValueError(f"duplicate field key: {f.key}")
            seen.add(f.key)
        # Normalise order to 0..N-1 based on current ordering.
        for idx, f in enumerate(sorted(self.fields, key=lambda x: x.order)):
            f.order = idx
        self.fields = sorted(self.fields, key=lambda x: x.order)
        return self


class QuestionnaireSubmission(BaseModel):
    """A single fill/edit session for a user's questionnaire."""

    submission_id: str
    agent_id: str
    external_user_id: str
    channel: str = "telegram"
    conversation_id: Optional[str] = None
    status: SubmissionStatus = SubmissionStatus.IN_PROGRESS
    source: SubmissionSource = SubmissionSource.FILL
    started_at: datetime
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


class QuestionnaireResponse(BaseModel):
    """Append-only row for a single field answer within a submission."""

    response_id: str
    submission_id: str
    agent_id: str
    external_user_id: str
    field_key: str
    value: str
    created_at: datetime
