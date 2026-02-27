"""Custom exceptions for API layer."""

from typing import Any, Optional


class AgentException(Exception):
    """Base exception for Agent application."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ):
        """Initialize exception."""
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


class AgentNotFoundError(AgentException):
    """Raised when agent is not found."""

    def __init__(self, agent_id: str):
        """Initialize exception."""
        super().__init__(
            message=f"Agent with ID '{agent_id}' not found",
            code="AGENT_NOT_FOUND",
            details={"agent_id": agent_id},
        )


class ConversationNotFoundError(AgentException):
    """Raised when conversation is not found."""

    def __init__(self, conversation_id: str):
        """Initialize exception."""
        super().__init__(
            message=f"Conversation with ID '{conversation_id}' not found",
            code="CONVERSATION_NOT_FOUND",
            details={"conversation_id": conversation_id},
        )


class InvalidAgentConfigError(AgentException):
    """Raised when agent configuration is invalid."""

    def __init__(self, message: str, validation_errors: Optional[dict[str, Any]] = None):
        """Initialize exception."""
        super().__init__(
            message=message,
            code="INVALID_AGENT_CONFIG",
            details={"validation_errors": validation_errors or {}},
        )


class EscalationError(AgentException):
    """Raised when escalation fails."""

    def __init__(self, message: str, escalation_type: Optional[str] = None):
        """Initialize exception."""
        super().__init__(
            message=message,
            code="ESCALATION_ERROR",
            details={"escalation_type": escalation_type} if escalation_type else {},
        )


class ModerationViolationError(AgentException):
    """Raised when content moderation violation is detected."""

    def __init__(self, message: str, categories: Optional[dict[str, bool]] = None):
        """Initialize exception."""
        super().__init__(
            message=message,
            code="MODERATION_VIOLATION",
            details={"categories": categories or {}},
        )


class RAGServiceError(AgentException):
    """Raised when RAG service fails."""

    def __init__(self, message: str, agent_id: Optional[str] = None):
        """Initialize exception."""
        super().__init__(
            message=message,
            code="RAG_SERVICE_ERROR",
            details={"agent_id": agent_id} if agent_id else {},
        )


class MessageProcessingError(AgentException):
    """Raised when message processing fails."""

    def __init__(self, message: str, conversation_id: Optional[str] = None):
        """Initialize exception."""
        super().__init__(
            message=message,
            code="MESSAGE_PROCESSING_ERROR",
            details={"conversation_id": conversation_id} if conversation_id else {},
        )








