"""LangChain chain for escalation detection."""

import hashlib
import json
import logging
from typing import Optional

from langchain_classic.chains import LLMChain
from langchain_classic.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.models.agent_config import AgentConfig
from app.models.escalation import (
    BUILTIN_CONTACT_RULE_ID,
    EscalationDecision,
    fail_closed_escalation_decision,
)
from app.services.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

ESCALATION_PROMPT_VERSION = 3


def _collect_escalation_rules(config: Optional[AgentConfig]) -> list[tuple[str, str, str]]:
    """Build (rule_id, title, criteria) tuples for the prompt."""
    rules: list[tuple[str, str, str]] = []
    if not config:
        rules.append(
            (
                BUILTIN_CONTACT_RULE_ID,
                "Contact info detection",
                "Escalate when the user shares a phone number or email address (any format, any language).",
            )
        )
        return rules

    esc = config.escalation
    if esc.detect_contact:
        rules.append(
            (
                BUILTIN_CONTACT_RULE_ID,
                "Contact info detection",
                "Escalate when the user shares a phone number or email address (any format, any language).",
            )
        )

    for i, rule in enumerate(esc.custom_rules or []):
        if not isinstance(rule, dict):
            continue
        name = (rule.get("name") or "").strip()
        desc = (rule.get("description") or "").strip()
        rid = (rule.get("id") or "").strip() or f"rule_{i}"
        if not desc:
            continue
        if not name:
            name = f"Custom rule {i + 1}"
        rules.append((rid, name, desc))

    for esc_type, instruction in (esc.instructions or {}).items():
        rid = f"legacy_{esc_type}"
        parts = [instruction.description.strip()]
        if instruction.guidance:
            parts.append(f"Guidance: {instruction.guidance.strip()}")
        if instruction.examples:
            ex = "\n".join(f"  - {e}" for e in instruction.examples[:5])
            parts.append(f"Examples:\n{ex}")
        criteria = "\n".join(parts)
        rules.append((rid, str(esc_type), criteria))

    return rules


def _build_rules_and_output_section(
    config: Optional[AgentConfig],
    rules: list[tuple[str, str, str]],
) -> str:
    policies_section = ""
    triggers_section = ""
    if config:
        escalation_config = config.escalation
        policies_dict: dict = {}
        if escalation_config.policies:
            policies_dict = dict(escalation_config.policies)
        else:
            if escalation_config.medical_question_policy:
                policies_dict["medical_question"] = escalation_config.medical_question_policy
            if escalation_config.urgent_case_policy:
                policies_dict["urgent_case"] = escalation_config.urgent_case_policy
            if escalation_config.repeat_patient_policy:
                policies_dict["repeat_patient"] = escalation_config.repeat_patient_policy
            if escalation_config.pre_procedure_policy:
                policies_dict["pre_procedure"] = escalation_config.pre_procedure_policy
        if policies_dict:
            policies_list = "\n".join(f"- {k}: {v}" for k, v in policies_dict.items())
            policies_section = f"\n\nEscalation policies (follow when they apply):\n{policies_list}"

        if escalation_config.triggers:
            triggers_list = []
            for trigger_type, keywords in escalation_config.triggers.items():
                if isinstance(keywords, list) and keywords:
                    kw = ", ".join(keywords[:10])
                    triggers_list.append(f"- {trigger_type}: {kw}")
            if triggers_list:
                triggers_section = (
                    "\n\nKeyword hints (examples only, not exhaustive):\n" + "\n".join(triggers_list)
                )

    if not rules and not policies_section and not triggers_section:
        return f"""No escalation rules are configured. Set needs_escalation to false and escalation_type to none.

Contact information extraction (always fill when present in the message):
- Phone numbers in any format; emails; empty lists if none

You MUST output one JSON object with EVERY field below.

Structured response fields:
- needs_escalation: boolean
- escalation_type: none
- confidence: float 0-1
- reason: brief explanation
- suggested_action: string
- matched_rule_ids: [] (empty)
- extracted_contacts: {{ "phone_numbers": [], "emails": [] }}"""

    lines = []
    for rid, title, criteria in rules:
        lines.append(f"- id `{rid}` | {title}\n  Criteria: {criteria}")

    rules_block = "Escalation rules (use exact `id` values in matched_rule_ids):\n" + "\n".join(lines)

    type_help = """
Escalation types (escalation_type):
- none — no rule matched; AI may continue
- booking — matched_rule_ids contains `__builtin_contact__` (contact info rule)
- custom — matched at least one custom rule (id not starting with legacy_)
- urgent | medical | repeat_patient — matched a legacy_* rule whose suffix matches that type; otherwise use custom

Consistency (mandatory):
- If matched_rule_ids is non-empty, needs_escalation MUST be true.
- If needs_escalation is true, matched_rule_ids MUST list every rule id that fired (at least one)."""

    extraction = """
Contact information extraction:
- Extract all phone numbers and emails found in the message (any format / language)
- If none, use empty lists in extracted_contacts

You MUST output one JSON object including EVERY field below (models often omit keys; all are required).

Structured response fields:
- needs_escalation: boolean
- escalation_type: one of none, booking, custom, urgent, medical, repeat_patient
- confidence: float between 0 and 1
- reason: brief explanation
- suggested_action: what should happen next
- matched_rule_ids: list of rule ids that matched (exact strings from the rules list)
- extracted_contacts: object with phone_numbers and emails (lists of strings)"""

    return f"""You are an escalation detection system for an AI agent.
Analyze the latest user message and conversation context. Decide if a human must take over.

{rules_block}{policies_section}{triggers_section}
{type_help}
{extraction}"""


class EscalationChain:
    """LangChain chain for detecting escalation needs."""

    def __init__(self, llm_factory: LLMFactory, agent_config: Optional[AgentConfig] = None):
        """Initialize escalation chain."""
        self.llm_factory = llm_factory
        self.agent_config = agent_config
        self._chains: dict[str, LLMChain] = {}

    def _make_cache_key(
        self,
        agent_id: Optional[str],
        agent_config: Optional[AgentConfig],
    ) -> str:
        """Build stable cache key based on escalation configuration."""
        base_key = agent_id or "default"
        if not agent_config:
            return f"{base_key}:v{ESCALATION_PROMPT_VERSION}"

        esc = agent_config.escalation
        relevant = {
            "prompt_v": ESCALATION_PROMPT_VERSION,
            "detect_contact": esc.detect_contact,
            "custom_rules": esc.custom_rules,
            "has_instructions": bool(esc.instructions),
            "instructions": {
                k: {
                    "description": v.description,
                    "guidance": v.guidance,
                    "examples": v.examples,
                }
                for k, v in esc.instructions.items()
            },
            "policies": esc.policies,
            "medical_question_policy": esc.medical_question_policy,
            "urgent_case_policy": esc.urgent_case_policy,
            "repeat_patient_policy": esc.repeat_patient_policy,
            "pre_procedure_policy": esc.pre_procedure_policy,
            "triggers": esc.triggers,
        }
        payload = json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        return f"{base_key}:{digest}"

    def _build_system_prompt(self, agent_config: Optional[AgentConfig] = None) -> str:
        rules = _collect_escalation_rules(agent_config)
        return _build_rules_and_output_section(agent_config, rules)

    def _escalation_llm_config(self, config: AgentConfig) -> AgentConfig:
        """Classifier: deterministic, bounded output size."""
        max_out = min(config.llm.max_output_tokens, 512)
        new_llm = config.llm.model_copy(update={"temperature": 0.0, "max_output_tokens": max_out})
        return config.model_copy(update={"llm": new_llm})

    async def _get_chain(
        self, agent_id: Optional[str] = None, agent_config: Optional[AgentConfig] = None
    ) -> LLMChain:
        """Get or create escalation chain (cached per agent_id + config hash)."""
        config = agent_config or self.agent_config
        cache_key = self._make_cache_key(agent_id=agent_id, agent_config=config)

        if cache_key not in self._chains:
            settings = get_settings()
            if config:
                llm_cfg = self._escalation_llm_config(config)
                llm = await self.llm_factory.get_chat_model(llm_cfg)
            else:
                from langchain_openai import ChatOpenAI

                client = await self.llm_factory.get_client(agent_id)
                llm = ChatOpenAI(
                    model=settings.openai_model,
                    temperature=0.0,
                    openai_api_key=client.api_key,
                    timeout=settings.openai_timeout,
                )

            system_prompt = self._build_system_prompt(config)
            logger.debug(
                "EscalationChain: creating new LLMChain. cache_key=%s agent_id=%s",
                cache_key,
                getattr(config, "agent_id", agent_id),
            )

            prompt_template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("human", "User message: {message}\n\nConversation context: {context}"),
                ]
            )
            output_parser = PydanticOutputParser(pydantic_object=EscalationDecision)
            self._chains[cache_key] = LLMChain(
                llm=llm,
                prompt=prompt_template,
                output_parser=output_parser,
            )

        return self._chains[cache_key]

    def _parse_chain_output(self, result: object) -> EscalationDecision:
        if isinstance(result, EscalationDecision):
            return result
        if isinstance(result, dict):
            if "text" in result:
                parsed = result["text"]
                if isinstance(parsed, EscalationDecision):
                    return parsed
                if isinstance(parsed, dict):
                    return EscalationDecision(**parsed)
                raise ValueError(f"Unexpected text payload type: {type(parsed)}")
            return EscalationDecision(**result)
        raise ValueError(f"Unexpected chain result type: {type(result)}")

    async def detect(
        self,
        message: str,
        context: Optional[dict] = None,
        agent_id: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> EscalationDecision:
        """Detect if escalation is needed. One retry on failure, then fail-closed."""
        chain = await self._get_chain(agent_id, agent_config)

        context_str = ""
        if context:
            context_str = f"Previous messages: {context.get('previous_messages', [])}"
            if context.get("conversation_status"):
                context_str += f"\nStatus: {context['conversation_status']}"
        if not context_str:
            context_str = "No previous context"

        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                result = await chain.ainvoke({"message": message, "context": context_str})
                decision = self._parse_chain_output(result)
                return decision
            except Exception as e:
                last_error = e
                logger.warning(
                    "EscalationChain.detect attempt %s failed: %s",
                    attempt + 1,
                    e,
                    exc_info=attempt == 1,
                )

        logger.error(
            "EscalationChain.detect failed after retries; fail-closed. last_error=%s",
            last_error,
            exc_info=True,
        )
        return fail_closed_escalation_decision()
