"""Models for Telegram user reminders."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ReminderCategory(str, Enum):
    VACCINATION = "vaccination"
    TREATMENT = "treatment"
    FOOD_ORDER = "food_order"
    OTHER = "other"


class ReminderScheduleKind(str, Enum):
    ONCE = "once"
    RECURRING = "recurring"


class ReminderStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class UserReminder(BaseModel):
    reminder_id: str
    agent_id: str
    binding_id: str
    external_user_id: str
    category: str
    schedule_kind: str
    schedule_spec: dict[str, Any] = Field(default_factory=dict)
    user_note: str = ""
    status: str
    next_fire_at: datetime
    last_fired_at: Optional[datetime] = None
    recurring_fires_done: int = 0
    created_at: datetime
    updated_at: datetime
    cancelled_at: Optional[datetime] = None
