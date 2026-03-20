"""Common API schemas and validators."""

import re
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error: dict[str, Any] = Field(
        ...,
        description="Error details",
        examples=[
            {
                "code": "AGENT_NOT_FOUND",
                "message": "Agent with ID 'example_agent' not found",
                "details": {"agent_id": "example_agent"},
                "request_id": "123e4567-e89b-12d3-a456-426614174000",
            }
        ],
    )


class SuccessResponse(BaseModel):
    """Standard success response schema."""

    success: bool = Field(default=True, description="Operation success flag")
    message: Optional[str] = Field(None, description="Success message")
    data: Optional[dict[str, Any]] = Field(None, description="Response data")


class PaginationParams(BaseModel):
    """Pagination parameters."""

    limit: int = Field(default=100, ge=1, le=1000, description="Number of items per page")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class AgentIDValidator:
    """Validator for agent IDs."""

    @staticmethod
    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Validate agent ID format."""
        if not v or not v.strip():
            raise ValueError("Agent ID cannot be empty")
        if len(v) > 100:
            raise ValueError("Agent ID cannot exceed 100 characters")
        # Allow alphanumeric, underscore, hyphen
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Agent ID can only contain alphanumeric characters, underscores, and hyphens"
            )
        return v.strip()


class ConversationIDValidator:
    """Validator for conversation IDs."""

    @staticmethod
    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, v: str) -> str:
        """Validate conversation ID format (UUID)."""
        try:
            UUID(v)
        except ValueError:
            raise ValueError("Conversation ID must be a valid UUID")
        return v


class MessageContentValidator:
    """Validator for message content."""

    @staticmethod
    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate message content."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        if len(v) > 10000:
            raise ValueError("Message content cannot exceed 10000 characters")
        return v.strip()








