"""Agent service - LangGraph-based orchestrator.

AgentChain now contains all pipeline logic (pre-moderation, escalation,
RAG, LLM, post-moderation, workflow transitions).  AgentService is
responsible for:
  - the pre-moderation fast path used by debounce scheduling
  - persisting the agent message to the database
  - sending the message through the channel sender
  - returning the agreed dict contract to callers
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Optional

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
        db: Any,
        channel_sender: Optional[ChannelSender] = None,
        organization_id: Optional[str] = None,
    ):
        self.agent_config = agent_config
        self.llm_factory = llm_factory
        self.escalation_service = escalation_service
        self.moderation_service = moderation_service
        self.rag_service = rag_service
        self.db = db
        self.channel_sender = channel_sender
        self.agent_chain = AgentChain(
            agent_config=agent_config,
            llm_factory=llm_factory,
            organization_id=organization_id,
        )

    async def run_pre_moderation_guard(
        self,
        user_message: str,
        conversation_id: str,
    ) -> Optional[dict]:
        """Pre-moderation only; used before debounce scheduling so toxic turns do not queue a reply."""
        if not self.agent_config.moderation.enabled:
            return None
        flagged, moderation_result = await self.moderation_service.check_pre_moderation(
            user_message, self.agent_config
        )
        if flagged:
            await self.db.update_conversation(
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
        return None

    async def process_message(
        self,
        user_message: str,
        conversation_id: str,
        conversation_history: Optional[list[dict]] = None,
        is_reply_stale: Optional[Callable[[], Awaitable[bool]]] = None,
        user_media_url: Optional[str] = None,
    ) -> dict:
        """Process a user message through the LangGraph workflow and return result dict.

        The dict contract is unchanged from the previous implementation so all
        callers (chat.py, websocket.py, agent_reply_coordinator.py, channel services)
        continue to work without modification.

        conversation_history is used only as a seed on the very first turn
        (when the LangGraph checkpoint for this conversation is empty).  On
        subsequent turns the checkpointer provides the full history, so passing
        history from PostgreSQL would cause duplicates.

        user_media_url: public URL of an image sent by the user.  When provided
        the image is passed natively to the LLM as a multimodal message
        (image_url content block) instead of a pre-converted text description.
        """
        from langchain_core.messages import AIMessage as _AIMessage, HumanMessage as _HumanMessage

        # Fast-path: stale check before doing any work
        if is_reply_stale and await is_reply_stale():
            return {
                "response": None,
                "escalate": False,
                "aborted": True,
                "agent_message_id": None,
            }

        # Build seed messages from conversation_history (used only on first turn).
        seed_messages = []
        if conversation_history:
            for msg in conversation_history[-50:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                role_lower = role.lower() if isinstance(role, str) else str(role).lower()
                if role_lower == "user":
                    seed_messages.append(_HumanMessage(content=content))
                elif role_lower == "agent":
                    seed_messages.append(_AIMessage(content=content))

        logger.info(
            "[vision] process_message: user_media_url=%r conversation_id=%s",
            user_media_url,
            conversation_id,
            extra={"conversation_id": conversation_id, "agent_id": self.agent_config.agent_id},
        )

        # Invoke the LangGraph graph — it handles pre-mod, escalation, RAG, LLM, post-mod, transitions
        try:
            graph_result = await self.agent_chain.generate_response(
                user_message=user_message,
                conversation_id=conversation_id,
                moderation_service=self.moderation_service,
                escalation_service=self.escalation_service,
                rag_service=self.rag_service,
                is_reply_stale=is_reply_stale,
                seed_messages=seed_messages,
                user_media_url=user_media_url,
            )
        except Exception as exc:
            logger.error(
                "Agent graph error for conversation %s: %s",
                conversation_id,
                exc,
                exc_info=True,
                extra={"conversation_id": conversation_id, "agent_id": self.agent_config.agent_id},
            )
            raise MessageProcessingError(
                f"Failed to generate response: {exc}",
                conversation_id=conversation_id,
            )

        # --- Escalation or moderation flagged from within the graph ---
        if graph_result.get("escalate"):
            escalation_type = graph_result.get("escalation_type")
            await self.db.update_conversation(
                conversation_id=conversation_id,
                status=ConversationStatus.NEEDS_HUMAN,
                handoff_reason=graph_result.get("escalation_reason", "Escalation"),
                **({"request_type": escalation_type} if escalation_type else {}),
            )
            logger.info(
                "Escalation from graph for conversation %s: %s",
                conversation_id,
                graph_result.get("escalation_reason"),
                extra={
                    "conversation_id": conversation_id,
                    "agent_id": self.agent_config.agent_id,
                    "escalation_type": escalation_type,
                },
            )
            return graph_result

        # --- Stale reply (aborted inside graph) ---
        if graph_result.get("aborted"):
            return graph_result

        response = graph_result.get("response") or ""
        rag_media_url = graph_result.get("rag_media_url")
        rag_media_type = graph_result.get("rag_media_type")

        # --- Schedule timer trigger if workflow requested one ---
        pending_timer = graph_result.get("pending_timer")
        if pending_timer:
            try:
                from app.chains.agent_chain import workflow_config_hash
                from app.services.agent_reply_coordinator import schedule_timer_trigger
                pending_timer["config_hash"] = workflow_config_hash(self.agent_config.workflow)
                await schedule_timer_trigger(conversation_id, pending_timer)
                logger.info(
                    "Timer trigger scheduled for conversation %s in %ds",
                    conversation_id,
                    pending_timer.get("delay_seconds"),
                    extra={"conversation_id": conversation_id, "agent_id": self.agent_config.agent_id},
                )
            except Exception as exc:
                logger.warning("Failed to schedule timer trigger: %s", exc)

        # --- Handle auto-step scheduling/cancellation ---
        if graph_result.get("cancel_all_auto_steps"):
            try:
                from app.services.agent_reply_coordinator import cancel_all_auto_steps
                await cancel_all_auto_steps(conversation_id)
            except Exception as exc:
                logger.warning("Failed to cancel auto-steps for %s: %s", conversation_id, exc)

        for sched in graph_result.get("pending_auto_schedules") or []:
            try:
                from app.chains.agent_chain import workflow_config_hash
                from app.services.agent_reply_coordinator import schedule_auto_step
                fire_at_ms = int(time.time() * 1000) + sched["delay_seconds"] * 1000
                await schedule_auto_step(
                    conversation_id,
                    auto_step=sched["auto_step"],
                    config_hash=workflow_config_hash(self.agent_config.workflow),
                    fire_at_ms=fire_at_ms,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to schedule auto-step %s for %s: %s",
                    sched.get("auto_step_id"),
                    conversation_id,
                    exc,
                )

        # --- Format response text for channel ---
        conversation = await self.db.get_conversation(conversation_id)
        channel_val = get_enum_value(conversation.channel) if conversation else None

        try:
            from app.utils.text_formatting import (
                clean_agent_response,
                format_agent_text_for_whatsapp,
            )
            if channel_val == MessageChannel.WHATSAPP.value:
                response = format_agent_text_for_whatsapp(response)
            else:
                cleaned = clean_agent_response(response)
                if cleaned is not None:
                    response = cleaned
        except Exception as exc:
            logger.error(
                "Failed to clean markdown for conversation %s: %s",
                conversation_id,
                exc,
                exc_info=True,
                extra={"conversation_id": conversation_id, "agent_id": self.agent_config.agent_id},
            )

        # --- Second stale check before persisting ---
        if is_reply_stale and await is_reply_stale():
            return {
                "response": None,
                "escalate": False,
                "aborted": True,
                "agent_message_id": None,
            }

        # --- Persist agent message ---
        agent_message_id = None
        agent_message_ts = None
        if conversation:
            agent_message_id = str(uuid.uuid4())
            msg_metadata: dict = {}
            if rag_media_url:
                msg_metadata["media_url"] = rag_media_url
                msg_metadata["media_type"] = rag_media_type
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
            await self.db.create_message(agent_message)
            agent_message_ts = to_utc_iso_string(agent_message.timestamp)

        # --- Send via channel sender (non-web channels) ---
        quick_replies: list[str] = graph_result.get("quick_replies") or []

        if self.channel_sender:
            try:
                if channel_val and channel_val != MessageChannel.WEB_CHAT.value:
                    await self.channel_sender.send_message(
                        conversation_id=conversation_id,
                        message_text=response,
                        media_url=rag_media_url,
                        media_type=rag_media_type,
                        quick_replies=quick_replies,
                    )
                    logger.info(
                        "Sent agent message for conversation %s (media=%s)",
                        conversation_id,
                        rag_media_type or "none",
                        extra={"conversation_id": conversation_id, "channel": channel_val},
                    )
            except Exception as exc:
                logger.error(
                    "Failed to send message through channel sender: %s",
                    exc,
                    exc_info=True,
                    extra={"conversation_id": conversation_id},
                )

        return {
            "response": response,
            "escalate": False,
            "rag_context_used": graph_result.get("rag_context_used", False),
            "rag_media_url": rag_media_url,
            "rag_media_type": rag_media_type,
            "agent_message_id": agent_message_id,
            "agent_message_timestamp": agent_message_ts,
            "quick_replies": quick_replies,
        }


def create_agent_service(
    agent_config: AgentConfig,
    db: Any,
    channel_sender: Optional[ChannelSender] = None,
    organization_id: Optional[str] = None,
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
        db=db,
        channel_sender=channel_sender,
        organization_id=organization_id,
    )
