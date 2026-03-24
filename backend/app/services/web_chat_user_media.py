"""Web chat user images: vision summary for agent (URL already on CDN)."""

import logging
from typing import Any

from app.services.image_processor_service import get_image_processor_service
from app.services.inbound_media_pipeline import compose_user_message_for_agent

logger = logging.getLogger(__name__)


async def enrich_web_chat_user_message_for_agent(
    caption: str,
    media_url: str | None,
    media_type: str | None,
    agent_id: str,
    agent_config: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return text for AgentService and metadata keys for the user Message (image_context, etc.)."""
    text = (caption or "").strip()
    extra: dict[str, Any] = {}

    if not media_url or (media_type or "").lower() != "image":
        return text, extra

    try:
        processor = get_image_processor_service()
        summary = await processor.describe_image_for_chat_context(
            media_url,
            agent_id=agent_id,
            agent_config=agent_config,
        )
    except Exception as exc:
        logger.warning(
            "Web chat image vision failed: %s",
            exc,
            exc_info=True,
        )
        return text, extra

    summary = (summary or "").strip()
    if not summary:
        return text, extra

    extra["image_context"] = summary
    extra["inbound_media_source"] = "web_chat"
    return compose_user_message_for_agent(caption or "", summary), extra
