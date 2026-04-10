"""Escalation service using LLM-based detection."""

import logging
from typing import Optional

from app.chains.escalation_chain import EscalationChain
from app.models.agent_config import AgentConfig
from app.models.escalation import (
    BUILTIN_CONTACT_RULE_ID,
    EscalationDecision,
    EscalationType,
    fail_closed_escalation_decision,
)
from app.services.llm_factory import LLMFactory, get_llm_factory

logger = logging.getLogger(__name__)


def _normalize_escalation_decision(decision: EscalationDecision) -> EscalationDecision:
    """Enforce consistency: non-empty matched_rule_ids implies escalation; map type from ids."""
    ids = [str(x).strip() for x in (decision.matched_rule_ids or []) if x and str(x).strip()]
    if not ids:
        return decision

    decision.needs_escalation = True
    decision.matched_rule_ids = ids
    decision.confidence = max(float(decision.confidence), 0.95)

    if BUILTIN_CONTACT_RULE_ID in ids:
        decision.escalation_type = EscalationType.BOOKING
        return decision

    legacy_hit: Optional[EscalationType] = None
    for rid in ids:
        if not rid.startswith("legacy_"):
            continue
        suffix = rid[len("legacy_") :]
        try:
            et = EscalationType(suffix)
        except ValueError:
            continue
        if et not in (EscalationType.NONE, EscalationType.CUSTOM):
            legacy_hit = et
            break

    if legacy_hit is not None:
        decision.escalation_type = legacy_hit
    else:
        decision.escalation_type = EscalationType.CUSTOM

    return decision


def _coerce_type_when_escalating(decision: EscalationDecision) -> None:
    """If model escalates but leaves type as none, avoid storing request_type='none'."""
    if not decision.needs_escalation:
        return
    val = getattr(decision.escalation_type, "value", decision.escalation_type)
    if str(val) == EscalationType.NONE.value:
        decision.escalation_type = EscalationType.CUSTOM


class EscalationService:
    """Service for detecting escalation needs."""

    def __init__(
        self,
        llm_factory: LLMFactory,
        agent_config: Optional[AgentConfig] = None,
        organization_id: Optional[str] = None,
    ):
        """Initialize escalation service."""
        self.llm_factory = llm_factory
        self.agent_config = agent_config
        self.escalation_chain = EscalationChain(
            llm_factory, agent_config, organization_id=organization_id
        )

    async def detect_escalation(
        self,
        message: str,
        conversation_context: Optional[dict] = None,
        agent_id: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> EscalationDecision:
        """Detect if message requires escalation using LLM-based detection."""
        config = agent_config or self.agent_config
        conv_id = (conversation_context or {}).get("conversation_id")

        try:
            decision = await self.escalation_chain.detect(
                message=message,
                context=conversation_context,
                agent_id=agent_id,
                agent_config=config,
            )
            decision = _normalize_escalation_decision(decision)
            _coerce_type_when_escalating(decision)

            if decision.extracted_contacts:
                c = decision.extracted_contacts
                if c.phone_numbers or c.emails:
                    _extra = {
                        "agent_id": agent_id,
                        "phone_numbers": c.phone_numbers,
                        "emails": c.emails,
                    }
                    if conv_id:
                        _extra["conversation_id"] = conv_id
                    logger.info(
                        "Contacts extracted: phones=%s, emails=%s",
                        c.phone_numbers,
                        c.emails,
                        extra=_extra,
                    )

            if decision.needs_escalation:
                escalation_type_str = getattr(
                    decision.escalation_type, "value", decision.escalation_type
                )
                _extra_esc = {
                    "agent_id": agent_id,
                    "escalation_type": escalation_type_str,
                    "confidence": decision.confidence,
                    "matched_rule_ids": decision.matched_rule_ids,
                    "has_contacts": decision.extracted_contacts is not None,
                }
                if conv_id:
                    _extra_esc["conversation_id"] = conv_id
                logger.info(
                    "Escalation detected: %s",
                    escalation_type_str,
                    extra=_extra_esc,
                )

            return decision
        except Exception as e:
            _err_extra = {"agent_id": agent_id, "message_length": len(message)}
            if conv_id:
                _err_extra["conversation_id"] = conv_id
            logger.error(
                "Escalation detection error for agent %s: %s",
                agent_id,
                e,
                exc_info=True,
                extra=_err_extra,
            )
            return fail_closed_escalation_decision()

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

        escalation_type_str = getattr(
            decision.escalation_type, "value", decision.escalation_type
        )

        reason_map = {
            EscalationType.URGENT.value: "Urgent medical situation detected",
            EscalationType.MEDICAL.value: "Medical question requiring human expertise",
            EscalationType.BOOKING.value: "User wants to book an appointment",
            EscalationType.REPEAT_PATIENT.value: "Returning patient - requires human handling",
            EscalationType.CUSTOM.value: "Custom escalation rule triggered",
            EscalationType.NONE.value: "No escalation needed",
        }

        return reason_map.get(str(escalation_type_str), decision.reason)


def create_escalation_service(
    agent_config: Optional[AgentConfig] = None,
    organization_id: Optional[str] = None,
) -> EscalationService:
    """Create escalation service instance with optional agent config."""
    llm_factory = get_llm_factory()
    return EscalationService(llm_factory, agent_config, organization_id=organization_id)


def get_escalation_service() -> EscalationService:
    """Get escalation service instance without agent config (backward compatibility)."""
    return create_escalation_service(None)
