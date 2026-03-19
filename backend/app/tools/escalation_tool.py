"""Tool for escalation detection."""

from typing import Optional

from pydantic import Field

from app.models.agent_config import AgentConfig
from app.tools.base import BaseAgentTool, ToolInput
from app.services.escalation_service import EscalationService


class EscalationToolInput(ToolInput):
    """Input for escalation tool."""

    message: str = Field(description="User message to check for escalation")
    context: Optional[dict] = Field(
        default=None, description="Conversation context"
    )


class EscalationTool(BaseAgentTool):
    """Tool for detecting escalation needs."""

    name: str = "escalation_detector"
    description: str = (
        "Detects if a user message requires escalation to a human admin. "
        "Use this when you need to determine if the conversation should be handed off. "
        "Always use this tool when you detect urgent situations, medical questions requiring diagnosis, "
        "booking requests, or when user indicates they are a returning patient."
    )

    def __init__(
        self,
        escalation_service: EscalationService,
        agent_id: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ):
        """Initialize escalation tool."""
        super().__init__(agent_id=agent_id)
        # Use object.__setattr__ to bypass Pydantic validation
        object.__setattr__(self, 'escalation_service', escalation_service)
        object.__setattr__(self, 'agent_config', agent_config)

    def _run(self, message: str, context: Optional[dict] = None) -> str:
        """Sync run (not used, but required by BaseTool)."""
        import asyncio

        return asyncio.run(self._arun(message, context))

    async def _arun(self, message: str, context: Optional[dict] = None) -> str:
        """Async run escalation detection."""
        decision = await self.escalation_service.detect_escalation(
            message=message,
            conversation_context=context,
            agent_id=self.agent_id,
            agent_config=self.agent_config,
        )

        if decision.needs_escalation:
            escalation_type_str = getattr(decision.escalation_type, "value", decision.escalation_type)
            return (
                f"ESCALATION NEEDED: {escalation_type_str}\n"
                f"Reason: {decision.reason}\n"
                f"Suggested action: {decision.suggested_action}\n"
                f"Confidence: {decision.confidence:.2f}"
            )
        else:
            return f"No escalation needed. Confidence: {decision.confidence:.2f}"

