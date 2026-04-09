"""Web chat user images: metadata enrichment for stored messages.

Architecture note (2025):
  The LLM now receives user images natively via a multimodal HumanMessage
  (image_url content block) passed directly through LangGraph.  This module
  no longer calls a pre-vision API to build a text description for the agent —
  that approach had a single point of failure and produced a weaker result.

  This module is kept for generating image_context metadata stored alongside
  the user Message record in the database (useful for search / history UI).
  It is NOT in the hot path of agent response generation.
"""

import logging
from typing import Any

from app.services.image_processor_service import get_image_processor_service

logger = logging.getLogger(__name__)


async def get_web_chat_image_metadata(
    media_url: str,
    agent_id: str,
    agent_config: dict[str, Any],
) -> dict[str, Any]:
    """Return metadata dict to attach to the stored user Message record.

    Calls the vision API to generate a text summary that is saved as
    ``image_context`` in the message metadata.  Failures are non-fatal:
    an empty dict is returned so the message is still saved correctly.
    """
    meta: dict[str, Any] = {"inbound_media_source": "web_chat"}
    try:
        processor = get_image_processor_service()
        summary = await processor.describe_image_for_chat_context(
            media_url,
            agent_id=agent_id,
            agent_config=agent_config,
        )
        summary = (summary or "").strip()
        if summary:
            meta["image_context"] = summary
    except Exception as exc:
        logger.warning(
            "Web chat image metadata vision failed (non-fatal): %s",
            exc,
            exc_info=True,
        )
    return meta
