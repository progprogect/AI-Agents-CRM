"""LangChain chain for escalation detection."""

from typing import Optional

from langchain_classic.chains import LLMChain
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.output_parsers import PydanticOutputParser

from app.config import get_settings
from app.models.agent_config import AgentConfig
from app.models.escalation import EscalationDecision, EscalationType
from app.services.llm_factory import LLMFactory


class EscalationChain:
    """LangChain chain for detecting escalation needs."""

    def __init__(self, llm_factory: LLMFactory, agent_config: Optional[AgentConfig] = None):
        """Initialize escalation chain."""
        self.llm_factory = llm_factory
        self.agent_config = agent_config
        self._chains: dict[str, LLMChain] = {}  # Cache per agent_id

    def _build_system_prompt(self, agent_config: Optional[AgentConfig] = None) -> str:
        """Build system prompt from agent config instructions or use default."""
        config = agent_config or self.agent_config

        detect_contact = config.escalation.detect_contact if config else True

        # Build escalation types based on config
        escalation_type_lines = []
        if detect_contact:
            escalation_type_lines.append(
                "- booking: User shares a phone number or email address (contact info detected) — always escalate"
            )
        escalation_type_lines.append("- custom: Custom escalation rule defined by the agent configuration")
        escalation_type_lines.append("- none: No escalation needed, AI can handle")

        base_types = "Escalation types:\n" + "\n".join(escalation_type_lines)

        # If no config or no instructions, use default prompt
        if not config or not config.escalation.instructions:
            return f"""You are an escalation detection system for an AI agent.
Your task is to analyze user messages and determine if they require human intervention.

{base_types}

IMPORTANT: Only escalate based on the rules above. Do NOT escalate for any other reason unless a custom rule explicitly defines it.

Contact Information Extraction:
When analyzing messages, also extract contact information:
- Phone numbers: Extract ALL phone numbers in ANY format (international like +1-555-123-4567, local like 8-800-555-35-35, with spaces/dashes/parentheses, written in different languages)
- Email addresses: Extract ALL email addresses found in the message
- Return contacts even if they're written in different languages, formats, or embedded in text
- If no contacts found, return empty lists

Return a structured response with:
- needs_escalation: boolean
- escalation_type: one of the types above
- confidence: float between 0 and 1
- reason: brief explanation
- suggested_action: what should happen next
- extracted_contacts: object with phone_numbers (list of strings) and emails (list of strings)"""

        # Build prompt from instructions
        instructions_section = []
        escalation_config = config.escalation

        # Add free-form custom rules (new format)
        if escalation_config.custom_rules:
            for rule in escalation_config.custom_rules:
                name = rule.get("name", "").strip()
                description = rule.get("description", "").strip()
                if name and description:
                    instructions_section.append(f"- {name}: {description}")

        # Add structured instructions (legacy format)
        for esc_type, instruction in escalation_config.instructions.items():
            examples_text = ""
            if instruction.examples:
                examples_list = "\n".join(f"  - {ex}" for ex in instruction.examples)
                examples_text = f"\nExamples:\n{examples_list}"

            instructions_section.append(
                f"- {esc_type}: {instruction.description}{examples_text}\n"
                f"  Guidance: {instruction.guidance}"
            )

        # Add policies if available (use policies dict or fallback to individual fields)
        policies_section = ""
        policies_dict = {}
        
        # Use policies dict if available, otherwise fallback to individual policy fields (backward compatibility)
        if escalation_config.policies:
            policies_dict = dict(escalation_config.policies)
        else:
            # Fallback to individual policy fields
            if escalation_config.medical_question_policy:
                policies_dict["medical_question"] = escalation_config.medical_question_policy
            if escalation_config.urgent_case_policy:
                policies_dict["urgent_case"] = escalation_config.urgent_case_policy
            if escalation_config.repeat_patient_policy:
                policies_dict["repeat_patient"] = escalation_config.repeat_patient_policy
            if escalation_config.pre_procedure_policy:
                policies_dict["pre_procedure"] = escalation_config.pre_procedure_policy
        
        if policies_dict:
            policies_list = "\n".join(
                f"- {k}: {v}" for k, v in policies_dict.items()
            )
            policies_section = f"\n\nEscalation Policies:\n{policies_list}"

        # Add trigger keywords as hints
        triggers_section = ""
        if escalation_config.triggers:
            triggers_list = []
            for trigger_type, keywords in escalation_config.triggers.items():
                if isinstance(keywords, list) and keywords:
                    keywords_str = ", ".join(keywords[:10])  # Limit to 10 keywords
                    triggers_list.append(f"- {trigger_type}: {keywords_str}")
            if triggers_list:
                triggers_section = f"\n\nKeyword Hints (examples, not exhaustive):\n" + "\n".join(triggers_list)

        # Build instructions text
        instructions_text = ""
        if instructions_section:
            instructions_text = f"\n\nEscalation Detection Instructions:\n{chr(10).join(instructions_section)}"
        
        return f"""You are an escalation detection system for an AI agent.
Your task is to analyze user messages and determine if they require human intervention.

{base_types}{instructions_text}{policies_section}{triggers_section}

IMPORTANT: Only escalate based on the rules defined above. Do NOT escalate for reasons not listed.

Contact Information Extraction:
When analyzing messages, also extract contact information:
- Phone numbers: Extract ALL phone numbers in ANY format (international like +1-555-123-4567, local like 8-800-555-35-35, with spaces/dashes/parentheses, written in different languages)
- Email addresses: Extract ALL email addresses found in the message
- Return contacts even if they're written in different languages, formats, or embedded in text
- If no contacts found, return empty lists

Return a structured response with:
- needs_escalation: boolean
- escalation_type: one of the types above
- confidence: float between 0 and 1
- reason: brief explanation
- suggested_action: what should happen next
- extracted_contacts: object with phone_numbers (list of strings) and emails (list of strings)"""

    async def _get_chain(
        self, agent_id: Optional[str] = None, agent_config: Optional[AgentConfig] = None
    ) -> LLMChain:
        """Get or create escalation chain (cached per agent_id)."""
        cache_key = agent_id or "default"
        config = agent_config or self.agent_config

        if cache_key not in self._chains:
            settings = get_settings()
            # Use agent's LLM when config available, else fallback to default OpenAI config
            if config:
                llm = await self.llm_factory.get_chat_model(config)
            else:
                from langchain_openai import ChatOpenAI
                client = await self.llm_factory.get_client(agent_id)
                llm = ChatOpenAI(
                    model=settings.openai_model,
                    temperature=0.5,
                    openai_api_key=client.api_key,
                    timeout=settings.openai_timeout,
                )

            # Build system prompt from config
            system_prompt = self._build_system_prompt(config)

            # Create prompt template
            prompt_template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    ("human", "User message: {message}\n\nConversation context: {context}"),
                ]
            )

            # Create output parser
            output_parser = PydanticOutputParser(pydantic_object=EscalationDecision)

            # Create chain
            self._chains[cache_key] = LLMChain(
                llm=llm,
                prompt=prompt_template,
                output_parser=output_parser,
            )

        return self._chains[cache_key]

    async def detect(
        self,
        message: str,
        context: Optional[dict] = None,
        agent_id: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
    ) -> EscalationDecision:
        """Detect if escalation is needed."""
        chain = await self._get_chain(agent_id, agent_config)

        # Prepare context string
        context_str = ""
        if context:
            context_str = f"Previous messages: {context.get('previous_messages', [])}"
            if context.get("conversation_status"):
                context_str += f"\nStatus: {context['conversation_status']}"

        try:
            result = await chain.ainvoke(
                {
                    "message": message,
                    "context": context_str or "No previous context",
                }
            )
            # LLMChain with PydanticOutputParser returns dict with 'text' key
            # The 'text' value contains the parsed EscalationDecision as dict
            if isinstance(result, dict):
                # Extract from 'text' key (LLMChain output format)
                if 'text' in result:
                    parsed = result['text']
                    if isinstance(parsed, EscalationDecision):
                        return parsed
                    elif isinstance(parsed, dict):
                        return EscalationDecision(**parsed)
                # If no 'text' key, try to create EscalationDecision directly from result
                return EscalationDecision(**result)
            # If result is already EscalationDecision, return as-is
            if isinstance(result, EscalationDecision):
                return result
            # Fallback: try to create from result
            return EscalationDecision(**result) if hasattr(result, '__dict__') else EscalationDecision(
                needs_escalation=False,
                escalation_type=EscalationType.NONE,
                confidence=0.0,
                reason=f"Unexpected result type: {type(result)}",
                suggested_action="continue_with_ai",
            )
        except Exception as e:
            # On error, default to no escalation
            return EscalationDecision(
                needs_escalation=False,
                escalation_type=EscalationType.NONE,
                confidence=0.0,
                reason=f"Error in escalation detection: {str(e)}",
                suggested_action="continue_with_ai",
            )

