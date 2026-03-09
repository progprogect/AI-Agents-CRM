"""Message models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.utils.datetime_utils import to_utc_iso_string, utc_now


class MessageRole(str, Enum):
    """Message role."""

    USER = "user"
    AGENT = "agent"
    ADMIN = "admin"


class MessageChannel(str, Enum):
    """Message channel type."""

    WEB_CHAT = "web_chat"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"


class Message(BaseModel):
    """Message model."""

    message_id: str = Field(..., description="Unique message identifier")
    conversation_id: str = Field(..., description="Conversation ID")
    agent_id: str = Field(..., description="Agent ID")
    role: MessageRole = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    channel: MessageChannel = Field(
        default=MessageChannel.WEB_CHAT, description="Channel through which message was sent/received"
    )
    external_message_id: Optional[str] = Field(
        None, description="External message ID (e.g., Instagram message ID)"
    )
    external_user_id: Optional[str] = Field(
        None, description="External user ID (e.g., Instagram user ID)"
    )
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    ttl: Optional[int] = Field(
        None, description="TTL timestamp for DynamoDB (timestamp + 48h)"
    )

    class Config:
        """Pydantic config."""

        use_enum_values = True
        json_encoders = {datetime: lambda v: to_utc_iso_string(v) if v else None}








