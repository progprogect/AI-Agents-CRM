"""LangChain chain for escalation detection."""

import hashlib
import json
import logging
from typing import Any, Optional

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
from app.utils.langchain_prompt import escape_braces_for_chat_template

logger = logging.getLogger(__name__)

# Bump when escalation system/human prompt text or how it is assembled changes so
# cached LLMChain instances in EscalationChain._chains are invalidated (long-lived workers).
ESCALATION_PROMPT_VERSION = 6

# Reserved value for EscalationConfig.medical_question_policy — expanded to a fixed classifier paragraph.
MEDICAL_QUESTION_POLICY_VET_INFORMATIONAL = "vet_informational"

_VET_INFORMATIONAL_EXPANDED = (
    "Do NOT escalate for general educational pet-care questions: vaccination schedules, "
    "nutrition basics, behavior and training, grooming, preventive care, when the user asks "
    "for information. The AI may answer from the knowledge base (RAG) with clear disclaimers; "
    "this is not a veterinary diagnosis. "
    "DO escalate for: (1) life-threatening emergency or severe acute distress; "
    "(2) user explicitly requests a human, wants to book an appointment, or shares phone/email; "
    "(3) repeat-patient flows per repeat_patient policy; "
    "(4) user asks for a diagnosis, prescription, individualized treatment plan, or lab "
    "interpretation for their specific animal. "
    "(RU: не эскалировать за общие вопросы о прививках, уходе, поведении; эскалировать при "
    "срочности, явной записи, контакте, повторном пациенте, запросе диагноза/назначения лечения "
    "под конкретное животное.)"
)


def expand_medical_question_policy_for_prompt(raw: str) -> str:
    """Map reserved policy tokens to full classifier text; pass through otherwise."""
    if raw == MEDICAL_QUESTION_POLICY_VET_INFORMATIONAL:
        return _VET_INFORMATIONAL_EXPANDED
    return raw


def _expand_policies_dict(policies: dict[str, str]) -> dict[str, str]:
    """Apply reserved tokens per policy key (currently medical_question only)."""
    out: dict[str, str] = {}
    for k, v in policies.items():
        if k == "medical_question" and isinstance(v, str):
            out[k] = expand_medical_question_policy_for_prompt(v)
        else:
            out[k] = v
    return out

# Classifier output cap (long system prompt + format_instructions needs headroom)
_ESCALATION_MAX_OUTPUT_TOKENS = 768

ESCALATION_JSON_ENVELOPE = """
Output format (strict):
- Reply with ONLY one valid JSON object matching the schema in the next section.
- Do not wrap in markdown code fences (no ```).
- No preamble, no explanation before or after the JSON.
"""

_ESCALATION_OUTPUT_PARSER = PydanticOutputParser(pydantic_object=EscalationDecision)


def _extract_llm_text(result: Any) -> str:
    """Normalize LLMChain / chat model return payload to a single string."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        t = result.get("text")
        if t is None:
            return ""
        if hasattr(t, "content"):
            content = getattr(t, "content", None)
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(str(block["text"]))
                    else:
                        parts.append(str(block))
                return "".join(parts).strip()
        if isinstance(t, str):
            return t.strip()
    return str(result).strip()


def _parse_escalation_json_lenient_dict(raw: str) -> dict:
    """Extract a JSON object from model output (markdown fences, leading prose)."""
    s = raw.strip()
    if "```" in s:
        for chunk in s.split("```"):
            chunk = chunk.strip()
            if chunk.lower().startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                s = chunk
                break
    start = s.find("{")
    if start < 0:
        raise ValueError("No JSON object found in escalation LLM output")
    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(s[start:])
    if not isinstance(obj, dict):
        raise ValueError("Escalation JSON root must be an object")
    return obj


def parse_escalation_from_llm_text(raw: str) -> EscalationDecision:
    """Try strict PydanticOutputParser, then lenient JSON + model_validate (fill_missing_llm_fields)."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty escalation LLM output")
    try:
        return _ESCALATION_OUTPUT_PARSER.parse(text)
    except Exception as first_err:
        logger.debug(
            "Escalation strict parse failed, trying lenient JSON: %s",
            first_err,
            exc_info=False,
        )
        data = _parse_escalation_json_lenient_dict(text)
        return EscalationDecision.model_validate(data)


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
            policies_dict = _expand_policies_dict(
                {str(k): str(v) for k, v in dict(escalation_config.policies).items()}
            )
        else:
            if escalation_config.medical_question_policy:
                policies_dict["medical_question"] = expand_medical_question_policy_for_prompt(
                    escalation_config.medical_question_policy
                )
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
            "enabled": esc.enabled,
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
        max_out = min(config.llm.max_output_tokens, _ESCALATION_MAX_OUTPUT_TOKENS)
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

            base_system = self._build_system_prompt(config)
            system_prompt = escape_braces_for_chat_template(
                f"{base_system}\n{ESCALATION_JSON_ENVELOPE}\n"
                f"{_ESCALATION_OUTPUT_PARSER.get_format_instructions()}"
            )
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
            # Parsing in detect(): strict parser first, then lenient JSON (phase 2 fallback).
            self._chains[cache_key] = LLMChain(llm=llm, prompt=prompt_template)

        return self._chains[cache_key]

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
                text = _extract_llm_text(result)
                decision = parse_escalation_from_llm_text(text)
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
