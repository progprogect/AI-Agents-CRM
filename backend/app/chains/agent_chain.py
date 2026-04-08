"""Main LangChain agent chain."""

import logging
from typing import Any, Optional

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.config import get_settings
from app.models.agent_config import AgentConfig
from app.services.llm_factory import LLMFactory
from app.tools.booking_tool import BookingTool

logger = logging.getLogger(__name__)


def _extract_final_ai_text(messages: list[BaseMessage]) -> str:
    """Take the last assistant turn without pending tool calls (LangGraph agent output)."""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            continue
        content: Any = msg.content
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
    return ""


class AgentChain:
    """Main agent chain for conversation."""

    def __init__(
        self,
        agent_config: AgentConfig,
        llm_factory: LLMFactory,
    ):
        """Initialize agent chain."""
        self.agent_config = agent_config
        self.llm_factory = llm_factory
        self._agent_graph: Any = None

    async def _get_agent_graph(self) -> Any:
        """Build LangChain 1.x agent graph (create_agent); one graph per AgentChain instance."""
        if self._agent_graph is not None:
            return self._agent_graph

        system_prompt = self._build_system_prompt()
        llm = await self.llm_factory.get_chat_model(self.agent_config)

        tools = [BookingTool(agent_id=self.agent_config.agent_id)]

        settings = get_settings()
        self._agent_graph = create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
            debug=settings.debug,
        )

        return self._agent_graph

    def _build_system_prompt(self) -> str:
        """Build system prompt from agent config."""
        prompts = self.agent_config.prompts.system

        # Format persona with profile information
        persona = prompts.get("persona", "").format(
            agent_display_name=self.agent_config.profile.agent_display_name,
            doctor_display_name=self.agent_config.profile.agent_display_name,
            company_display_name=self.agent_config.profile.company_display_name,
            specialty=self.agent_config.profile.specialty,
        )

        hard_rules = prompts.get("hard_rules", "")
        goal = prompts.get("goal", "")

        # Build profile information section
        profile = self.agent_config.profile
        languages_str = ", ".join(profile.languages)
        profile_info = f"""
Profile Information:
- Agent: {profile.agent_display_name}
- Company: {profile.company_display_name}
- Specialty: {profile.specialty}
- Languages: {languages_str}

You can communicate in these languages.
You must always respond only in the same language used by the user in their current message.
If the user switches language, switch to that language immediately.
Do not mix languages in one response unless the user explicitly asks for it.
"""

        # Build style description from config
        style = self.agent_config.style
        style_description = f"""
Communication Style Guidelines:
- Tone: {style.tone.replace('_', ' ').title()}
- Formality Level: {style.formality.replace('_', ' ').title()}
- Empathy Level: {style.empathy_level}/10 (higher = more empathetic and understanding)
- Depth Level: {style.depth_level}/10 (higher = more detailed responses)
- Message Length: {style.message_length.replace('_', ' ').title()}
- Persuasion Approach: {style.persuasion.title()} (soft = gentle suggestions, strong = more direct)

Apply these style guidelines consistently in all your responses. Adjust your communication to match these parameters while maintaining professionalism and medical safety.
"""

        response_policy = """
Response Policy (strict priority):
1) Safety and hard rules
2) Escalation rules
3) Retrieved RAG context
4) Approved examples

Language:
- Respond only in the language of the user's current message
- If user switches language, switch immediately
- Do not mix languages unless the user explicitly requests it

Grounding:
- Use only grounded sources: RAG context, approved examples, and escalation rules
- Never invent, assume, or add facts beyond these sources
- If required information is missing, state it clearly and offer escalation to a human admin
- Keep answers factual and concise; avoid broad recommendations or opinions without source facts
- Do not speculate about logistics details (transport routes, parking availability, walking convenience, timing) unless explicitly present in grounded sources
- For location/directions questions without concrete data, provide only confirmed address/contact details and ask a clarifying question or offer handoff
"""

        # Build few-shot examples section (English only)
        examples_section = ""
        if self.agent_config.prompts.examples:
            examples_list = []
            for i, example in enumerate(self.agent_config.prompts.examples, 1):
                examples_list.append(
                    f"Example {i}:\n"
                    f"User: {example.user_message}\n"
                    f"Agent: {example.agent_response}"
                )

            examples_section = f"""
Examples of desired communication style:

{chr(10).join(examples_list)}

Use examples as response patterns, not as exact scripts.
If a user question is similar to an example, use that example answer as a base and adapt it
to the current request, conversation context, and grounded facts.
Do not copy sensitive or irrelevant details verbatim.
If multiple examples are relevant, combine them into one coherent response.
If examples conflict with safety, hard rules, escalation guidance, or RAG context, those rules win.
"""

        escalation_section = ""
        escalation_lines: list[str] = []
        for i, rule in enumerate(self.agent_config.escalation.custom_rules or []):
            if not isinstance(rule, dict):
                continue
            name = (rule.get("name") or "").strip()
            desc = (rule.get("description") or "").strip()
            if not desc:
                continue
            label = name or f"Rule {i + 1}"
            escalation_lines.append(f"- {label}: {desc}")
        for esc_type, instruction in self.agent_config.escalation.instructions.items():
            examples_text = ""
            if instruction.examples:
                examples_list = "\n".join(f"  - {ex}" for ex in instruction.examples[:3])
                examples_text = f"\n  Examples: {examples_list}"
            escalation_lines.append(
                f"- {esc_type}: {instruction.description}{examples_text}"
            )
        if escalation_lines:
            escalation_section = f"""
Human handoff (platform-controlled):
Escalation to a human is evaluated automatically before you see the user's message. If you are generating a reply, the conversation is currently allowed to continue under those rules.

Align your tone and boundaries with these configured expectations (there is no separate escalation tool in this agent):

{chr(10).join(escalation_lines)}
"""

        # Build final prompt with proper spacing
        prompt_parts = [
            persona,
            profile_info,
            hard_rules,
            goal,
            style_description,
            response_policy,
        ]

        if examples_section:
            prompt_parts.append(examples_section)

        if escalation_section:
            prompt_parts.append(escalation_section)

        prompt_parts.append("""Remember:
- Be friendly and professional
- Never provide medical diagnoses or treatment advice
- For urgent or medical situations, direct the user toward appropriate care and human support per your guidelines above (handoff is handled by the system when rules require it)
- Help with booking appointments
- Use available tools when needed

When context includes "Image: URL", you may suggest relevant images in your response.
Use format: [Image: URL] or ![description](URL) for the user to view.
""")

        return "\n\n".join(prompt_parts)

    # Marker the LLM must include when it wants to attach a RAG document to the response.
    ATTACH_MEDIA_MARKER = "[ATTACH_MEDIA]"

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        rag_context: Optional[str] = None,
        rag_media_available: bool = False,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Generate response using LangChain create_agent graph."""
        graph = await self._get_agent_graph()

        # Prepare input with context (explicit markers; retrieved text is not user-authored)
        input_text = user_message
        if rag_context:
            input_text = (
                "---BEGIN_RETRIEVED_CONTEXT---\n"
                f"{rag_context}\n"
                "---END_RETRIEVED_CONTEXT---\n\n"
                f"User message: {user_message}"
            )
            if rag_media_available:
                input_text += (
                    "\n\nImportant: Some context documents have attached files (images, PDFs). "
                    "Only include [ATTACH_MEDIA] at the end of your response when the user "
                    "explicitly asks for a document, file, price list, or when attaching would "
                    "directly help answer their question. Do NOT include [ATTACH_MEDIA] for "
                    "greetings, simple questions, or casual conversation."
                )

        messages_lc: list[BaseMessage] = []
        if conversation_history:
            for msg in conversation_history[-50:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                role_lower = role.lower() if isinstance(role, str) else str(role).lower()
                if role_lower == "user":
                    messages_lc.append(HumanMessage(content=content))
                elif role_lower == "agent":
                    messages_lc.append(AIMessage(content=content))

        messages_lc.append(HumanMessage(content=input_text))

        if messages_lc[:-1]:
            logger.debug(
                f"Chat history prepared: {len(messages_lc) - 1} messages",
                extra={
                    "agent_id": self.agent_config.agent_id,
                    "conversation_id": conversation_id,
                    "history_length": len(messages_lc) - 1,
                    "first_message_preview": (
                        messages_lc[0].content[:50] + "..."
                        if isinstance(messages_lc[0].content, str) and len(messages_lc[0].content) > 50
                        else str(messages_lc[0].content)[:50]
                    ),
                    "last_message_preview": (
                        messages_lc[-2].content[:50] + "..."
                        if isinstance(messages_lc[-2].content, str) and len(messages_lc[-2].content) > 50
                        else str(messages_lc[-2].content)[:50]
                    ),
                    "current_user_message_preview": user_message[:50] + "..."
                    if len(user_message) > 50
                    else user_message,
                },
            )
        else:
            logger.debug(
                "No chat history available (new conversation)",
                extra={
                    "agent_id": self.agent_config.agent_id,
                    "conversation_id": conversation_id,
                    "current_user_message_preview": user_message[:50] + "..."
                    if len(user_message) > 50
                    else user_message,
                },
            )

        meta: dict[str, str] = {"agent_id": self.agent_config.agent_id}
        if conversation_id:
            meta["conversation_id"] = conversation_id

        try:
            result = await graph.ainvoke(
                {"messages": messages_lc},
                config=RunnableConfig(tags=["agent_chat"], metadata=meta),
            )
            out_messages = result.get("messages") or []
            text = _extract_final_ai_text(out_messages)
            if text:
                return text
            return "I apologize, but I couldn't generate a response."
        except Exception as e:
            logger.error(
                f"Error generating response: {str(e)}",
                exc_info=True,
                extra={
                    "agent_id": self.agent_config.agent_id,
                    "conversation_id": conversation_id,
                    "history_length": len(messages_lc) - 1,
                    "user_message_preview": user_message[:100] if user_message else None,
                },
            )
            return f"I apologize, but I encountered an error: {str(e)}"
