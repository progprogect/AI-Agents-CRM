"""Service for conversation management."""

from datetime import datetime, timezone
from typing import Any, Optional

from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageRole
from app.services.agent_service import AgentService, create_agent_service
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value


def _to_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def build_conversation_history_for_agent(
    dynamodb: Any,
    conversation_id: str,
    last_user_message_for_dedup: str,
    *,
    limit: int = 50,
    agent_context_reset_at: Optional[datetime] = None,
) -> list[dict]:
    """Build chronological chat history for the LLM and drop duplicate last user turn.

    If agent_context_reset_at is set, only messages strictly after that instant are included.
    """
    history_messages = await dynamodb.list_messages(
        conversation_id=conversation_id,
        limit=limit,
        reverse=True,
    )
    if agent_context_reset_at is not None:
        reset_utc = _to_utc_aware(agent_context_reset_at)
        history_messages = [
            m for m in history_messages if _to_utc_aware(m.timestamp) > reset_utc
        ]
    conversation_history = [
        {
            "role": get_enum_value(msg.role),
            "content": msg.content,
        }
        for msg in reversed(history_messages)
    ]
    if conversation_history:
        last_msg = conversation_history[-1]
        if (
            last_msg.get("role", "").lower() == "user"
            and last_msg.get("content", "").strip() == last_user_message_for_dedup.strip()
        ):
            conversation_history = conversation_history[:-1]
    return conversation_history


class ConversationService:
    """Service for managing conversations and processing messages."""

    def __init__(self, dynamodb: Any):
        """Initialize conversation service."""
        self.dynamodb = dynamodb

    async def process_message(
        self,
        conversation_id: str,
        user_message: str,
        agent_service: AgentService,
    ) -> dict:
        """Process user message and return agent response."""
        # Get conversation
        conversation = await self.dynamodb.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        conversation_history = await build_conversation_history_for_agent(
            self.dynamodb,
            conversation_id,
            user_message,
            agent_context_reset_at=conversation.agent_context_reset_at,
        )

        # Process through agent service
        result = await agent_service.process_message(
            user_message=user_message,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
        )

        return result

    async def send_agent_response(
        self,
        conversation_id: str,
        agent_response: str,
        metadata: Optional[dict] = None,
    ) -> Message:
        """Create and save agent response message."""
        import uuid

        # Get conversation to get agent_id
        conversation = await self.dynamodb.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Create agent message
        message_id = str(uuid.uuid4())
        agent_message = Message(
            message_id=message_id,
            conversation_id=conversation_id,
            agent_id=conversation.agent_id,
            role=MessageRole.AGENT,
            content=agent_response,
            channel=conversation.channel,
            external_user_id=conversation.external_user_id,
            timestamp=utc_now(),
            metadata=metadata or {},
        )

        await self.dynamodb.create_message(agent_message)

        # Update conversation status if needed
        # Handle both enum and string status (from DynamoDB)
        status_value = get_enum_value(conversation.status)
        if status_value != ConversationStatus.AI_ACTIVE.value:
            await self.dynamodb.update_conversation(
                conversation_id=conversation_id,
                status=ConversationStatus.AI_ACTIVE,
            )

        return agent_message




