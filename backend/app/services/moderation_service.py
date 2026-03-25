"""Moderation service — dispatches to OpenAI Moderations API or Gemini JSON classifier."""

import logging
from functools import lru_cache
from typing import Optional

from app.models.agent_config import AgentConfig
from app.models.moderation import ModerationCategory, ModerationResult
from app.services.llm_factory import LLMFactory, get_llm_factory
from app.services.moderation_backends import moderate_for_agent

logger = logging.getLogger(__name__)


class ModerationService:
    """Service for content moderation."""

    def __init__(self, llm_factory: LLMFactory):
        """Initialize moderation service."""
        self.llm_factory = llm_factory

    async def moderate(self, content: str, agent_config: AgentConfig) -> ModerationResult:
        """Moderate content using the agent's moderation provider and model."""
        try:
            return await moderate_for_agent(content, agent_config, self.llm_factory)
        except Exception as e:
            logger.error(
                f"Moderation error for agent {agent_config.agent_id}: {str(e)}",
                exc_info=True,
                extra={"agent_id": agent_config.agent_id, "content_length": len(content)},
            )
            return ModerationResult(
                flagged=False,
                categories={},
                category_scores={},
                category=ModerationCategory.NONE,
            )

    async def check_pre_moderation(
        self, message: str, agent_config: AgentConfig
    ) -> tuple[bool, Optional[ModerationResult]]:
        """Check message before processing (pre-moderation)."""
        result = await self.moderate(message, agent_config)
        return result.flagged, result if result.flagged else None

    async def check_post_moderation(
        self, response: str, agent_config: AgentConfig
    ) -> tuple[bool, Optional[ModerationResult]]:
        """Check agent response after generation (post-moderation)."""
        result = await self.moderate(response, agent_config)
        return result.flagged, result if result.flagged else None


@lru_cache()
def get_moderation_service() -> ModerationService:
    """Get cached moderation service instance."""
    llm_factory = get_llm_factory()
    return ModerationService(llm_factory)
