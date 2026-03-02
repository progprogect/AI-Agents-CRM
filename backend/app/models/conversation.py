"""Conversation models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.models.message import MessageChannel
from app.utils.datetime_utils import to_utc_iso_string, utc_now


class ConversationStatus(str, Enum):
    """Status of a conversation."""

    AI_ACTIVE = "AI_ACTIVE"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    HUMAN_ACTIVE = "HUMAN_ACTIVE"
    CLOSED = "CLOSED"


class MarketingStatus(str, Enum):
    """Marketing status of a conversation for CRM tracking."""

    NEW = "NEW"
    BOOKED = "BOOKED"
    NO_RESPONSE = "NO_RESPONSE"
    REJECTED = "REJECTED"


class Conversation(BaseModel):
    """Conversation model."""

    conversation_id: str = Field(..., description="Unique conversation identifier")
    agent_id: str = Field(..., description="Agent ID this conversation belongs to")
    channel: MessageChannel = Field(
        default=MessageChannel.WEB_CHAT, description="Channel through which conversation is conducted"
    )
    external_conversation_id: Optional[str] = Field(
        None, description="External conversation ID (e.g., Instagram thread ID)"
    )
    external_user_id: Optional[str] = Field(
        None, description="External user ID (e.g., Instagram user ID)"
    )
    status: ConversationStatus = Field(
        default=ConversationStatus.AI_ACTIVE, description="Current conversation status"
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    closed_at: Optional[datetime] = Field(None, description="When conversation was closed")
    handoff_reason: Optional[str] = Field(
        None, description="Reason for handoff to human"
    )
    request_type: Optional[str] = Field(
        None, description="Type of request: info, booking, escalation"
    )
    ttl: Optional[int] = Field(
        None, description="TTL timestamp for DynamoDB (created_at + 48h)"
    )
    # Instagram user profile fields (populated from profile table when fetching)
    external_user_name: Optional[str] = Field(
        None, description="Instagram user display name"
    )
    external_user_username: Optional[str] = Field(
        None, description="Instagram username"
    )
    external_user_profile_pic: Optional[str] = Field(
        None, description="Instagram profile picture URL"
    )
    # Marketing status fields for CRM tracking (legacy — use crm_stage_id)
    marketing_status: Optional[MarketingStatus] = Field(
        default=MarketingStatus.NEW, description="Marketing status for CRM tracking (legacy)"
    )
    rejection_reason: Optional[str] = Field(
        None, description="Reason for rejection (required when marketing_status is REJECTED)"
    )
    crm_stage_id: Optional[str] = Field(
        None, description="CRM pipeline stage UUID"
    )

    class Config:
        """Pydantic config."""

        use_enum_values = True
        json_encoders = {datetime: lambda v: to_utc_iso_string(v) if v else None}








