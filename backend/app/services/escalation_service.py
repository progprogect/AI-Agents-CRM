"""Escalation service using LLM-based detection."""

import logging
from typing import Optional

from app.chains.escalation_chain import EscalationChain
from app.models.agent_config import AgentConfig
from app.models.escalation import EscalationDecision, EscalationType
from app.services.llm_factory import LLMFactory, get_llm_factory

logger = logging.getLogger(__name__)


class EscalationService:
    """Service for detecting escalation needs."""

    def __init__(self, llm_factory: LLMFactory, agent_config: Optional[AgentConfig] = None):
        """Initialize escalation service."""
        self.llm_factory = llm_factory
        self.agent_config = agent_config
        self.escalation_chain = EscalationChain(llm_factory, agent_config)

    async def detect_escalation(
        self,
        message: str,
        conversation_context: Optional[dict] = None,
        agent_id: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> EscalationDecision:
        """Detect if message requires escalation using LLM-based detection."""
        # Use provided agent_config or fallback to instance config
        config = agent_config or self.agent_config

        try:
            # LLM-based detection with contact extraction
            decision = await self.escalation_chain.detect(
                message=message,
                context=conversation_context,
                agent_id=agent_id,
                agent_config=config,
            )

            # Process extracted contacts from LLM
            detect_contact = config.escalation.detect_contact if config else True
            if decision.extracted_contacts:
                contacts = decision.extracted_contacts

                # Log extracted contacts if any found
                if contacts.phone_numbers or contacts.emails:
                    logger.info(
                        f"Contacts extracted: phones={contacts.phone_numbers}, emails={contacts.emails}",
                        extra={
                            "agent_id": agent_id,
                            "phone_numbers": contacts.phone_numbers,
                            "emails": contacts.emails,
                        },
                    )

                if detect_contact:
                    # If phone numbers found but no escalation yet, trigger booking escalation
                    if contacts.phone_numbers and not decision.needs_escalation:
                        decision.needs_escalation = True
                        decision.escalation_type = EscalationType.BOOKING
                        decision.confidence = max(decision.confidence, 0.9)
                        decision.reason = f"Phone number(s) detected: {', '.join(contacts.phone_numbers)}"
                        decision.suggested_action = "handoff_for_booking"
                        logger.info(
                            f"Escalation triggered by phone number detection",
                            extra={
                                "agent_id": agent_id,
                                "phone_numbers": contacts.phone_numbers,
                            },
                        )
                    # If escalation already detected and phone numbers found, enhance reason
                    elif contacts.phone_numbers and decision.needs_escalation:
                        if decision.escalation_type == EscalationType.BOOKING:
                            decision.reason = f"{decision.reason} (Phone: {', '.join(contacts.phone_numbers)})"
                            decision.confidence = min(decision.confidence + 0.1, 1.0)

            if decision.needs_escalation:
                logger.info(
                    f"Escalation detected: {decision.escalation_type.value}",
                    extra={
                        "agent_id": agent_id,
                        "escalation_type": decision.escalation_type.value,
                        "confidence": decision.confidence,
                        "has_contacts": decision.extracted_contacts is not None,
                    },
                )

            return decision
        except Exception as e:
            logger.error(
                f"Escalation detection error for agent {agent_id}: {str(e)}",
                exc_info=True,
                extra={"agent_id": agent_id, "message_length": len(message)},
            )
            # On error, default to no escalation to avoid blocking conversation
            return EscalationDecision(
                needs_escalation=False,
                escalation_type=EscalationType.NONE,
                confidence=0.0,
                reason=f"Error in escalation detection: {str(e)}",
                suggested_action="continue_with_ai",
            )

    async def should_escalate(
        self,
        message: str,
        conversation_context: Optional[dict] = None,
        agent_id: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> tuple[bool, EscalationDecision]:
        """Check if escalation is needed and return decision."""
        decision = await self.detect_escalation(
            message=message,
            conversation_context=conversation_context,
            agent_id=agent_id,
            agent_config=agent_config,
        )
        return decision.needs_escalation, decision

    def get_escalation_reason(self, decision: EscalationDecision) -> str:
        """Get human-readable escalation reason."""
        if not decision.needs_escalation:
            return "No escalation needed"

        reason_map = {
            EscalationType.URGENT: "Urgent medical situation detected",
            EscalationType.MEDICAL: "Medical question requiring human expertise",
            EscalationType.BOOKING: "User wants to book an appointment",
            EscalationType.REPEAT_PATIENT: "Returning patient - requires human handling",
            EscalationType.NONE: "No escalation needed",
        }

        return reason_map.get(decision.escalation_type, decision.reason)


def create_escalation_service(
    agent_config: Optional[AgentConfig] = None,
) -> EscalationService:
    """Create escalation service instance with optional agent config."""
    llm_factory = get_llm_factory()
    return EscalationService(llm_factory, agent_config)


# Keep backward compatibility
def get_escalation_service() -> EscalationService:
    """Get escalation service instance without agent config (backward compatibility)."""
    return create_escalation_service(None)

