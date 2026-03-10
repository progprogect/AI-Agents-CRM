"""Agent service - LangChain orchestrator."""

import logging
import re
import uuid
from typing import Optional

from app.api.exceptions import MessageProcessingError
from app.chains.agent_chain import AgentChain
from app.models.agent_config import AgentConfig
from app.models.conversation import ConversationStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.channel_sender import ChannelSender
from app.services.escalation_service import EscalationService, create_escalation_service
from app.services.llm_factory import LLMFactory, get_llm_factory
from app.services.moderation_service import ModerationService, get_moderation_service
from app.services.rag_service import RAGService, get_rag_service
from app.storage.dynamodb import DynamoDBClient
from app.utils.datetime_utils import to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)


class AgentService:
    """Service for agent orchestration."""

    def __init__(
        self,
        agent_config: AgentConfig,
        llm_factory: LLMFactory,
        escalation_service: EscalationService,
        moderation_service: ModerationService,
        rag_service: RAGService,
        dynamodb: DynamoDBClient,
        channel_sender: Optional[ChannelSender] = None,
    ):
        """Initialize agent service."""
        self.agent_config = agent_config
        self.llm_factory = llm_factory
        self.escalation_service = escalation_service
        self.moderation_service = moderation_service
        self.rag_service = rag_service
        self.dynamodb = dynamodb
        self.channel_sender = channel_sender
        self.agent_chain = AgentChain(
            agent_config=agent_config,
            llm_factory=llm_factory,
            escalation_service=escalation_service,
            rag_service=rag_service,
        )

    async def process_message(
        self,
        user_message: str,
        conversation_id: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> dict:
        """Process user message and generate response."""
        # Pre-moderation check
        if self.agent_config.moderation.enabled:
            flagged, moderation_result = await self.moderation_service.check_pre_moderation(
                user_message, self.agent_config.agent_id
            )
            if flagged:
                # Update conversation status
                await self.dynamodb.update_conversation(
                    conversation_id=conversation_id,
                    status=ConversationStatus.NEEDS_HUMAN,
                    handoff_reason="Content moderation violation",
                )
                return {
                    "response": None,
                    "escalate": True,
                    "escalation_reason": "Content moderation violation",
                    "moderation_result": moderation_result,
                }

        # Escalation detection
        escalation_decision = await self.escalation_service.detect_escalation(
            message=user_message,
            conversation_context={
                "conversation_id": conversation_id,
                "previous_messages": conversation_history or [],
            },
            agent_id=self.agent_config.agent_id,
            agent_config=self.agent_config,
        )

        if escalation_decision.needs_escalation:
            # Update conversation status
            await self.dynamodb.update_conversation(
                conversation_id=conversation_id,
                status=ConversationStatus.NEEDS_HUMAN,
                handoff_reason=escalation_decision.reason,
                request_type=escalation_decision.escalation_type.value,
            )

            result = {
                "response": None,
                "escalate": True,
                "escalation_reason": escalation_decision.reason,
                "escalation_type": escalation_decision.escalation_type.value,
            }
            
            # Include extracted contacts if available
            if escalation_decision.extracted_contacts:
                contacts = escalation_decision.extracted_contacts
                result["extracted_contacts"] = {
                    "phone_numbers": contacts.phone_numbers,
                    "emails": contacts.emails,
                }
                logger.info(
                    f"Extracted contacts included in escalation result",
                    extra={
                        "conversation_id": conversation_id,
                        "phone_numbers": contacts.phone_numbers,
                        "emails": contacts.emails,
                    },
                )
            
            return result

        # Retrieve RAG context (text + any media attachments) in one DB call
        rag_context = None
        rag_media_list: list = []
        rag_media_attachment = None   # first eligible RAGMediaAttachment, or None
        if self.agent_config.rag.enabled:
            try:
                rag_context, rag_media_list = await self.rag_service.get_context_and_media(
                    query=user_message,
                    agent_id=self.agent_config.agent_id,
                    agent_config=self.agent_config,
                    top_k=self.agent_config.rag.retrieval.get("top_k", 6),
                    score_threshold=self.agent_config.rag.retrieval.get("score_threshold", 0.2),
                )
                if rag_context:
                    logger.debug(
                        f"RAG context retrieved for conversation {conversation_id}",
                        extra={
                            "conversation_id": conversation_id,
                            "agent_id": self.agent_config.agent_id,
                            "context_length": len(rag_context),
                            "media_attachments": len(rag_media_list),
                        },
                    )
                # Take the highest-scored media item (already sorted by RAG search)
                if rag_media_list:
                    rag_media_attachment = rag_media_list[0]
                    logger.info(
                        "RAG media attachment selected for conversation %s: %s (%s, score=%.3f)",
                        conversation_id,
                        rag_media_attachment["title"],
                        rag_media_attachment["media_type"],
                        rag_media_attachment["score"],
                        extra={"conversation_id": conversation_id},
                    )
            except Exception as e:
                # Log error but continue without RAG
                logger.warning(
                    f"RAG retrieval error for conversation {conversation_id}: {str(e)}",
                    exc_info=True,
                    extra={
                        "conversation_id": conversation_id,
                        "agent_id": self.agent_config.agent_id,
                    },
                )

        # Generate response
        try:
            response = await self.agent_chain.generate_response(
                user_message=user_message,
                conversation_history=conversation_history,
                rag_context=rag_context,
                rag_media_available=bool(rag_media_list),
            )

            # Normalize: some LLM backends (e.g. Claude via LangChain) return a list
            # of content blocks instead of a plain string.
            if isinstance(response, list):
                parts = []
                for item in response:
                    if isinstance(item, dict):
                        parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        parts.append(item)
                response = "".join(parts).strip()

            # Strip internal Claude safety/processing markers that leak into output
            response = re.sub(
                r"^\[(?:SAFETY_HANDLER|THINKING|INTERNAL|SYSTEM|TOOL_USE)\][^\n]*\n?",
                "",
                response,
                flags=re.IGNORECASE,
            ).strip()

            if not response or not response.strip():
                logger.warning(
                    f"Empty response generated for conversation {conversation_id}",
                    extra={
                        "conversation_id": conversation_id,
                        "agent_id": self.agent_config.agent_id,
                    },
                )
                response = "I apologize, but I couldn't generate a response. Please try again."
            
            # Only attach RAG media when LLM explicitly requested it via [ATTACH_MEDIA]
            if rag_media_attachment and AgentChain.ATTACH_MEDIA_MARKER not in response:
                rag_media_attachment = None
            if AgentChain.ATTACH_MEDIA_MARKER in response:
                response = response.replace(AgentChain.ATTACH_MEDIA_MARKER, "").strip()

            # Clean markdown formatting for plain text channels (Instagram, etc.)
            try:
                from app.utils.text_formatting import clean_agent_response
                cleaned = clean_agent_response(response)
                if cleaned is not None:
                    response = cleaned
            except Exception as e:
                logger.error(
                    f"Failed to clean markdown for conversation {conversation_id}: {str(e)}",
                    exc_info=True,
                    extra={
                        "conversation_id": conversation_id,
                        "agent_id": self.agent_config.agent_id,
                    },
                )
                # Continue with original response if cleaning fails
        except Exception as e:
            logger.error(
                f"Response generation error for conversation {conversation_id}: {str(e)}",
                exc_info=True,
                extra={
                    "conversation_id": conversation_id,
                    "agent_id": self.agent_config.agent_id,
                },
            )
            raise MessageProcessingError(
                f"Failed to generate response: {str(e)}",
                conversation_id=conversation_id,
            )

        # Post-moderation check
        if self.agent_config.moderation.enabled:
            flagged, moderation_result = await self.moderation_service.check_post_moderation(
                response, self.agent_config.agent_id
            )
            if flagged:
                # Update conversation status
                await self.dynamodb.update_conversation(
                    conversation_id=conversation_id,
                    status=ConversationStatus.NEEDS_HUMAN,
                    handoff_reason="Generated content moderation violation",
                )
                return {
                    "response": None,
                    "escalate": True,
                    "escalation_reason": "Generated content moderation violation",
                    "moderation_result": moderation_result,
                }

        # Save agent message to database first
        conversation = await self.dynamodb.get_conversation(conversation_id)
        agent_message_id = None
        if conversation:
            agent_message_id = str(uuid.uuid4())
            msg_metadata: dict = {}
            if rag_media_attachment:
                msg_metadata["media_url"] = rag_media_attachment["url"]
                msg_metadata["media_type"] = rag_media_attachment["media_type"]
            agent_message = Message(
                message_id=agent_message_id,
                conversation_id=conversation_id,
                agent_id=conversation.agent_id,
                role=MessageRole.AGENT,
                content=response,
                channel=conversation.channel,
                external_user_id=conversation.external_user_id,
                timestamp=utc_now(),
                metadata=msg_metadata,
            )
            await self.dynamodb.create_message(agent_message)

        # Send message through channel sender if provided and not web chat.
        # For web chat, delivery is handled by WebSocket in websocket.py;
        # the media metadata saved above will be picked up when the frontend polls.
        if self.channel_sender:
            try:
                conversation_channel = get_enum_value(conversation.channel) if conversation else None
                if conversation_channel and conversation_channel != MessageChannel.WEB_CHAT.value:
                    await self.channel_sender.send_message(
                        conversation_id=conversation_id,
                        message_text=response,
                        media_url=rag_media_attachment["url"] if rag_media_attachment else None,
                        media_type=rag_media_attachment["media_type"] if rag_media_attachment else None,
                    )
                    logger.info(
                        "Sent agent message for conversation %s (media=%s)",
                        conversation_id,
                        rag_media_attachment["media_type"] if rag_media_attachment else "none",
                        extra={
                            "conversation_id": conversation_id,
                            "channel": conversation_channel,
                        },
                    )
            except Exception as e:
                logger.error(
                    f"Failed to send message through channel sender: {e}",
                    exc_info=True,
                    extra={"conversation_id": conversation_id},
                )
                # Don't fail the whole request if channel sending fails

        result = {
            "response": response,
            "escalate": False,
            "rag_context_used": bool(rag_context),
            "rag_media_url": rag_media_attachment["url"] if rag_media_attachment else None,
            "rag_media_type": rag_media_attachment["media_type"] if rag_media_attachment else None,
            "agent_message_id": agent_message_id,
            "agent_message_timestamp": to_utc_iso_string(agent_message.timestamp) if conversation and agent_message_id else None,
        }
        return result


def create_agent_service(
    agent_config: AgentConfig,
    dynamodb: DynamoDBClient,
    channel_sender: Optional[ChannelSender] = None,
) -> AgentService:
    """Create agent service instance."""
    llm_factory = get_llm_factory()
    escalation_service = create_escalation_service(agent_config)
    moderation_service = get_moderation_service()
    rag_service = get_rag_service()

    return AgentService(
        agent_config=agent_config,
        llm_factory=llm_factory,
        escalation_service=escalation_service,
        moderation_service=moderation_service,
        rag_service=rag_service,
        dynamodb=dynamodb,
        channel_sender=channel_sender,
    )

