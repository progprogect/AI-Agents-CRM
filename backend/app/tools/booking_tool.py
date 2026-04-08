"""Tool for booking intent detection (not registered on AgentChain in the current product build)."""

from typing import Optional

from app.tools.base import BaseAgentTool, ToolInput
from pydantic import Field


class BookingToolInput(ToolInput):
    """Input for booking tool."""

    message: str = Field(description="User message to check for booking intent")


class BookingTool(BaseAgentTool):
    """Tool for detecting booking intent."""

    name: str = "booking_detector"
    description: str = (
        "Detects if a user wants to book an appointment. "
        "Use this to identify booking requests."
    )

    def _run(self, message: str) -> str:
        """Sync run (not used, but required by BaseTool)."""
        import asyncio

        return asyncio.run(self._arun(message))

    async def _arun(self, message: str) -> str:
        """Async run booking detection."""
        # Simple keyword-based detection for MVP
        # Can be enhanced with LLM later
        booking_keywords = [
            "записаться",
            "запись",
            "приём",
            "консультация",
            "appointment",
            "book",
            "schedule",
        ]

        message_lower = message.lower()
        found_keywords = [
            kw for kw in booking_keywords if kw in message_lower
        ]

        if found_keywords:
            return (
                f"BOOKING INTENT DETECTED\n"
                f"Keywords found: {', '.join(found_keywords)}\n"
                f"Action: Request phone number for booking"
            )
        else:
            return "No booking intent detected"








