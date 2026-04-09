"""Main LangChain / LangGraph agent chain.

When workflow.enabled=False (default), the graph runs as a simple single-step
conversation identical to the previous create_agent behaviour.

When workflow.enabled=True, the StateGraph drives a configurable multi-step
scenario with named steps, conditional transitions, forced steps, and
timer-based follow-ups.

IMPORTANT: Services (ModerationService, EscalationService, RAGService) and
callbacks (is_reply_stale) are intentionally NOT stored in WorkflowState.
LangGraph's PostgresSaver serialises the full state to msgpack; Python service
objects are not serialisable.  Instead, these are captured via per-call
closures in _build_call_graph() and are available to each node function
without touching the persisted state.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Optional

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.config import get_settings
from app.models.agent_config import AgentConfig, WorkflowConfig, WorkflowStep

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WorkflowState  — only serialisable fields go here
# ---------------------------------------------------------------------------

class WorkflowState(TypedDict):
    """Persisted conversation state.  All fields must be msgpack-serialisable."""

    messages: Annotated[list[AnyMessage], add_messages]
    """Full conversation history (managed by LangGraph add_messages reducer)."""

    user_message: str
    """Raw text of the current user turn (without RAG context wrapping)."""

    current_step_id: str
    """Identifier of the active workflow step."""

    step_history: list[str]
    """Ordered list of step ids visited so far (oldest first)."""

    collected: dict[str, str]
    """Variables collected from the user during the conversation."""

    pending_timer: Optional[dict]
    """Scheduled timer trigger: {delay_seconds, message_template, step_id, fire_at_ms}."""

    rag_context: Optional[str]
    """Retrieved context text — persisted so nodes downstream can read it."""

    rag_media_list: list
    """Media attachments returned by RAG retrieval."""

    result: Optional[dict]
    """Final output dict — matches the contract expected by AgentService.process_message."""

    # Transient per-turn scratch fields (persisted between nodes within one turn,
    # overwritten on every new turn so safe to checkpoint as plain strings).
    llm_response: str
    step_system_prompt: str

    agent_id: str
    conversation_id: str


# ---------------------------------------------------------------------------
# Graph structure cache (keyed by agent_id + sha256 of workflow config)
# NOTE: we cache the *compiled graph* built without per-call closures.
# Per-call services are injected via closures in _build_call_graph().
# ---------------------------------------------------------------------------

_graph_cache: dict[str, Any] = {}


def _graph_cache_key(agent_id: str, workflow: WorkflowConfig) -> str:
    payload = json.dumps(workflow.model_dump(), sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return f"{agent_id}:{digest}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATTACH_MEDIA_MARKER = "[ATTACH_MEDIA]"


def _normalise_llm_text(content: Any) -> str:
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
    return str(content).strip()


def _clean_response(text: str) -> str:
    text = re.sub(
        r"^\[(?:SAFETY_HANDLER|THINKING|INTERNAL|SYSTEM|TOOL_USE)\][^\n]*\n?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return text


# ---------------------------------------------------------------------------
# AgentChain
# ---------------------------------------------------------------------------

class AgentChain:
    """Builds and caches a LangGraph StateGraph for an agent."""

    ATTACH_MEDIA_MARKER = ATTACH_MEDIA_MARKER

    def __init__(self, agent_config: AgentConfig, llm_factory: Any) -> None:
        self.agent_config = agent_config
        self.llm_factory = llm_factory

    # ------------------------------------------------------------------
    # System-prompt construction
    # ------------------------------------------------------------------

    def _build_base_system_prompt(self) -> str:
        prompts = self.agent_config.prompts.system

        persona = prompts.get("persona", "").format(
            agent_display_name=self.agent_config.profile.agent_display_name,
            doctor_display_name=self.agent_config.profile.agent_display_name,
            company_display_name=self.agent_config.profile.company_display_name,
            specialty=self.agent_config.profile.specialty,
        )

        hard_rules = prompts.get("hard_rules", "")
        goal = prompts.get("goal", "")

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

        style = self.agent_config.style
        style_description = f"""
Communication Style Guidelines:
- Tone: {style.tone.replace('_', ' ').title()}
- Formality Level: {style.formality.replace('_', ' ').title()}
- Empathy Level: {style.empathy_level}/10 (higher = more empathetic and understanding)
- Depth Level: {style.depth_level}/10 (higher = more detailed responses)
- Message Length: {style.message_length.replace('_', ' ').title()}
- Persuasion Approach: {style.persuasion.title()} (soft = gentle suggestions, strong = more direct)

Apply these style guidelines consistently in all your responses.
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

Grounding:
- Use only grounded sources: RAG context, approved examples, and escalation rules
- Never invent, assume, or add facts beyond these sources
- If required information is missing, state it clearly and offer escalation to a human admin
- Keep answers factual and concise
- Do not speculate about logistics details unless explicitly present in grounded sources
"""

        examples_section = ""
        if self.agent_config.prompts.examples:
            examples_list = [
                f"Example {i}:\nUser: {ex.user_message}\nAgent: {ex.agent_response}"
                for i, ex in enumerate(self.agent_config.prompts.examples, 1)
            ]
            examples_section = f"""
Examples of desired communication style:

{chr(10).join(examples_list)}

Use examples as response patterns, not exact scripts.
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
                ex_text = "\n".join(f"  - {e}" for e in instruction.examples[:3])
                examples_text = f"\n  Examples:\n{ex_text}"
            escalation_lines.append(f"- {esc_type}: {instruction.description}{examples_text}")
        if escalation_lines:
            escalation_section = f"""
Human handoff (platform-controlled):
Escalation is evaluated automatically before you see the user's message. If you are generating a reply, the conversation is currently allowed to continue.

{chr(10).join(escalation_lines)}
"""

        parts = [persona, profile_info, hard_rules, goal, style_description, response_policy]
        if examples_section:
            parts.append(examples_section)
        if escalation_section:
            parts.append(escalation_section)
        parts.append("""Remember:
- Be friendly and professional
- Never provide medical diagnoses or treatment advice
- For urgent or medical situations, direct toward appropriate care and human support

When context includes "Image: URL", you may suggest relevant images in your response.
Use format: [Image: URL] or ![description](URL) for the user to view.
""")
        return "\n\n".join(parts)

    @staticmethod
    def _build_step_system_prompt(base_prompt: str, step: WorkflowStep, collected: dict[str, str]) -> str:
        lines = [base_prompt, f"\n--- Current workflow step: {step.name} ---"]
        lines.append(step.instructions)
        if step.collect:
            missing = [v for v in step.collect if v not in collected]
            if missing:
                lines.append(f"\nPlease collect the following information from the user: {', '.join(missing)}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Per-call graph construction
    # All service objects are captured in closures — they never touch state.
    # ------------------------------------------------------------------

    def _build_call_graph(
        self,
        *,
        moderation_service: Any,
        escalation_service: Any,
        rag_service: Any,
        llm: Any,
        is_reply_stale: Optional[Callable[[], Awaitable[bool]]],
    ) -> Any:
        """Build a compiled graph with services captured in node closures.

        This graph is NOT cached because the closures hold per-request
        objects (services, llm instance, stale callback).
        """
        agent_config = self.agent_config
        agent_chain_self = self

        # ---- Node: pre_moderation ----
        async def node_pre_moderation(state: WorkflowState) -> dict:
            if moderation_service is None or not agent_config.moderation.enabled:
                return {}
            flagged, mod_result = await moderation_service.check_pre_moderation(
                state["user_message"], agent_config
            )
            if flagged:
                return {
                    "result": {
                        "response": None,
                        "escalate": True,
                        "escalation_reason": "Content moderation violation",
                        "moderation_result": mod_result,
                    }
                }
            return {}

        # ---- Node: escalation_node ----
        async def node_escalation(state: WorkflowState) -> dict:
            if escalation_service is None or not agent_config.escalation.enabled:
                return {}
            decision = await escalation_service.detect_escalation(
                message=state["user_message"],
                conversation_context={"conversation_id": state["conversation_id"]},
                agent_id=state["agent_id"],
                agent_config=agent_config,
            )
            if decision.needs_escalation:
                esc_type = getattr(decision.escalation_type, "value", decision.escalation_type)
                result: dict = {
                    "response": None,
                    "escalate": True,
                    "escalation_reason": decision.reason,
                    "escalation_type": esc_type,
                }
                if decision.extracted_contacts:
                    result["extracted_contacts"] = {
                        "phone_numbers": decision.extracted_contacts.phone_numbers,
                        "emails": decision.extracted_contacts.emails,
                    }
                return {"result": result}
            return {}

        # ---- Node: workflow_router ----
        async def node_workflow_router(state: WorkflowState) -> dict:
            wf = agent_config.workflow
            if not wf.enabled or not wf.steps:
                return {"current_step_id": "default"}

            current = state.get("current_step_id") or wf.start_step_id
            step_map = {s.id: s for s in wf.steps}

            if current not in step_map:
                current = wf.start_step_id

            history = state.get("step_history", [])
            if history:
                last_step = step_map.get(history[-1])
                if last_step:
                    for tr in last_step.transitions:
                        if tr.is_forced and tr.next_step_id != current:
                            logger.info(
                                "Forced transition blocks navigation from %s; staying on %s",
                                current,
                                last_step.id,
                                extra={
                                    "conversation_id": state["conversation_id"],
                                    "agent_id": state["agent_id"],
                                },
                            )
                            current = last_step.id
                            break

            return {"current_step_id": current}

        # ---- Node: step_executor ----
        async def node_step_executor(state: WorkflowState) -> dict:
            base_prompt = agent_chain_self._build_base_system_prompt()
            wf = agent_config.workflow
            step_id = state.get("current_step_id", "default")
            step_map = {s.id: s for s in (wf.steps or [])}
            step = step_map.get(step_id)

            if step is not None:
                system_text = AgentChain._build_step_system_prompt(
                    base_prompt, step, state.get("collected", {})
                )
            else:
                system_text = base_prompt

            return {"step_system_prompt": system_text}

        # ---- Node: rag_retrieval ----
        async def node_rag_retrieval(state: WorkflowState) -> dict:
            if rag_service is None or not agent_config.rag.enabled:
                return {"rag_context": None, "rag_media_list": []}
            try:
                context, media_list = await rag_service.get_context_and_media(
                    query=state["user_message"],
                    agent_id=state["agent_id"],
                    agent_config=agent_config,
                    top_k=agent_config.rag.retrieval.get("top_k", 6),
                    score_threshold=agent_config.rag.retrieval.get("score_threshold", 0.2),
                )
                return {"rag_context": context, "rag_media_list": media_list or []}
            except Exception as exc:
                logger.warning(
                    "RAG retrieval error: %s",
                    exc,
                    extra={"conversation_id": state["conversation_id"], "agent_id": state["agent_id"]},
                )
                return {"rag_context": None, "rag_media_list": []}

        # ---- Node: llm_generate ----
        async def node_llm_generate(state: WorkflowState) -> dict:
            system_text: str = state.get("step_system_prompt") or ""
            rag_context = state.get("rag_context")
            rag_media_list = state.get("rag_media_list") or []
            user_message = state["user_message"]

            input_text = user_message
            if rag_context:
                input_text = (
                    "---BEGIN_RETRIEVED_CONTEXT---\n"
                    f"{rag_context}\n"
                    "---END_RETRIEVED_CONTEXT---\n\n"
                    f"User message: {user_message}"
                )
                if rag_media_list:
                    input_text += (
                        "\n\nImportant: Some context documents have attached files (images, PDFs). "
                        "Only include [ATTACH_MEDIA] at the end of your response when the user "
                        "explicitly asks for a document, file, price list, or when attaching would "
                        "directly help answer their question. Do NOT include [ATTACH_MEDIA] for "
                        "greetings, simple questions, or casual conversation."
                    )

            msgs: list[BaseMessage] = [SystemMessage(content=system_text)]
            for m in (state.get("messages") or []):
                msgs.append(m)
            msgs.append(HumanMessage(content=input_text))

            try:
                ai_msg: AIMessage = await llm.ainvoke(msgs)
                response_text = _clean_response(_normalise_llm_text(ai_msg.content))
                if not response_text:
                    response_text = "I apologize, but I couldn't generate a response. Please try again."
                updated_ai = AIMessage(content=response_text)
                return {"messages": [updated_ai], "llm_response": response_text}
            except Exception as exc:
                logger.error(
                    "LLM generation error: %s",
                    exc,
                    exc_info=True,
                    extra={"conversation_id": state["conversation_id"], "agent_id": state["agent_id"]},
                )
                err_msg = f"I apologize, but I encountered an error: {exc}"
                return {"messages": [AIMessage(content=err_msg)], "llm_response": err_msg}

        # ---- Node: post_moderation ----
        async def node_post_moderation(state: WorkflowState) -> dict:
            if moderation_service is None or not agent_config.moderation.enabled:
                return {}
            response_text = state.get("llm_response", "")
            if not response_text:
                return {}
            flagged, mod_result = await moderation_service.check_post_moderation(
                response_text, agent_config
            )
            if flagged:
                return {
                    "result": {
                        "response": None,
                        "escalate": True,
                        "escalation_reason": "Generated content moderation violation",
                        "moderation_result": mod_result,
                    }
                }
            return {}

        # ---- Node: transition_evaluator ----
        async def node_transition_evaluator(state: WorkflowState) -> dict:
            wf = agent_config.workflow
            if not wf.enabled or not wf.steps:
                return {}

            step_id = state.get("current_step_id", wf.start_step_id)
            step_map = {s.id: s for s in wf.steps}
            step = step_map.get(step_id)
            if step is None or not step.transitions:
                return {}

            conversation_summary = "\n".join(
                f"{type(m).__name__}: {_normalise_llm_text(getattr(m, 'content', ''))[:200]}"
                for m in (state.get("messages") or [])[-6:]
            )

            new_step_id = step_id
            new_collected = dict(state.get("collected", {}))
            timer_to_schedule = state.get("pending_timer")

            for transition in step.transitions:
                eval_prompt = (
                    f"Evaluate whether the following condition is satisfied based on the conversation.\n"
                    f"Condition: {transition.condition}\n\n"
                    f"Recent conversation:\n{conversation_summary}\n\n"
                    "Reply with exactly 'YES' or 'NO'."
                )
                try:
                    eval_result = await llm.ainvoke([HumanMessage(content=eval_prompt)])
                    answer = _normalise_llm_text(eval_result.content).upper().strip()
                except Exception as exc:
                    logger.warning("Transition evaluator LLM error: %s", exc)
                    answer = "NO"

                if answer.startswith("YES"):
                    new_step_id = transition.next_step_id
                    break
                elif transition.is_forced:
                    logger.debug(
                        "Forced transition condition not met for step %s; staying",
                        step_id,
                        extra={"conversation_id": state["conversation_id"]},
                    )
                    new_step_id = step_id
                    break

            history = list(state.get("step_history", []))
            if not history or history[-1] != new_step_id:
                history.append(new_step_id)

            if new_step_id != step_id:
                new_step = step_map.get(new_step_id)
                if new_step and new_step.timer_trigger:
                    tt = new_step.timer_trigger
                    fire_at_ms = int(time.time() * 1000) + tt.delay_seconds * 1000
                    timer_to_schedule = {
                        "delay_seconds": tt.delay_seconds,
                        "message_template": tt.message_template,
                        "step_id": new_step_id,
                        "fire_at_ms": fire_at_ms,
                    }
                else:
                    timer_to_schedule = None

            return {
                "current_step_id": new_step_id,
                "step_history": history,
                "collected": new_collected,
                "pending_timer": timer_to_schedule,
            }

        # ---- Node: output_collector ----
        async def node_output_collector(state: WorkflowState) -> dict:
            if state.get("result"):
                return {}

            if is_reply_stale is not None and await is_reply_stale():
                return {
                    "result": {
                        "response": None,
                        "escalate": False,
                        "aborted": True,
                        "agent_message_id": None,
                    }
                }

            response_text = state.get("llm_response", "")
            rag_media_list = state.get("rag_media_list") or []
            rag_context = state.get("rag_context")

            rag_media_attachment = None
            if rag_media_list and ATTACH_MEDIA_MARKER in response_text:
                rag_media_attachment = rag_media_list[0]
            response_text = response_text.replace(ATTACH_MEDIA_MARKER, "").strip()

            return {
                "result": {
                    "response": response_text,
                    "escalate": False,
                    "rag_context_used": bool(rag_context),
                    "rag_media_url": rag_media_attachment["url"] if rag_media_attachment else None,
                    "rag_media_type": rag_media_attachment["media_type"] if rag_media_attachment else None,
                    "pending_timer": state.get("pending_timer"),
                }
            }

        # ---- Routing ----
        def _route_pre_mod(state: WorkflowState) -> str:
            return "escalation" if not state.get("result") else "output_collector"

        def _route_escalation(state: WorkflowState) -> str:
            return "workflow_router" if not state.get("result") else "output_collector"

        def _route_post_mod(state: WorkflowState) -> str:
            return "transition_evaluator" if not state.get("result") else "output_collector"

        # ---- Assemble ----
        g = StateGraph(WorkflowState)

        g.add_node("pre_moderation", node_pre_moderation)
        g.add_node("escalation", node_escalation)
        g.add_node("workflow_router", node_workflow_router)
        g.add_node("step_executor", node_step_executor)
        g.add_node("rag_retrieval", node_rag_retrieval)
        g.add_node("llm_generate", node_llm_generate)
        g.add_node("post_moderation", node_post_moderation)
        g.add_node("transition_evaluator", node_transition_evaluator)
        g.add_node("output_collector", node_output_collector)

        g.set_entry_point("pre_moderation")
        g.add_conditional_edges("pre_moderation", _route_pre_mod)
        g.add_conditional_edges("escalation", _route_escalation)
        g.add_edge("workflow_router", "step_executor")
        g.add_edge("step_executor", "rag_retrieval")
        g.add_edge("rag_retrieval", "llm_generate")
        g.add_edge("llm_generate", "post_moderation")
        g.add_conditional_edges("post_moderation", _route_post_mod)
        g.add_edge("transition_evaluator", "output_collector")
        g.add_edge("output_collector", END)

        # Attach checkpointer for persistent workflow state (step progress, collected vars)
        try:
            from app.storage.postgres_checkpointer import get_checkpointer
            checkpointer = get_checkpointer()
            compiled = g.compile(checkpointer=checkpointer)
        except Exception:
            compiled = g.compile()

        return compiled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[list[dict]] = None,
        rag_context: Optional[str] = None,
        rag_media_available: bool = False,
        conversation_id: Optional[str] = None,
        moderation_service: Any = None,
        escalation_service: Any = None,
        rag_service: Any = None,
        is_reply_stale: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> dict:
        """Invoke the workflow graph and return the result dict."""
        llm = await self.llm_factory.get_chat_model(self.agent_config)

        # Build a per-call graph with services captured in closures
        graph = self._build_call_graph(
            moderation_service=moderation_service,
            escalation_service=escalation_service,
            rag_service=rag_service,
            llm=llm,
            is_reply_stale=is_reply_stale,
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

        wf = self.agent_config.workflow
        initial_step = wf.start_step_id if wf.enabled else "default"

        init_state: dict = {
            "messages": messages_lc,
            "user_message": user_message,
            "current_step_id": initial_step,
            "step_history": [],
            "collected": {},
            "pending_timer": None,
            "rag_context": None,
            "rag_media_list": [],
            "result": None,
            "llm_response": "",
            "step_system_prompt": "",
            "agent_id": self.agent_config.agent_id,
            "conversation_id": conversation_id or "",
        }

        meta: dict[str, str] = {"agent_id": self.agent_config.agent_id}
        if conversation_id:
            meta["conversation_id"] = conversation_id

        rc = RunnableConfig(
            tags=["agent_chat"],
            metadata=meta,
            configurable={"thread_id": conversation_id or self.agent_config.agent_id},
        )

        logger.debug(
            "Invoking agent graph",
            extra={
                "agent_id": self.agent_config.agent_id,
                "conversation_id": conversation_id,
                "workflow_enabled": wf.enabled,
                "step_id": initial_step,
                "history_length": len(messages_lc),
            },
        )

        try:
            final_state = await graph.ainvoke(init_state, config=rc)
            result = final_state.get("result") or {
                "response": "I apologize, but I couldn't generate a response.",
                "escalate": False,
                "rag_context_used": False,
                "rag_media_url": None,
                "rag_media_type": None,
            }
            return result
        except Exception as exc:
            logger.error(
                "Agent graph invocation failed: %s",
                exc,
                exc_info=True,
                extra={"agent_id": self.agent_config.agent_id, "conversation_id": conversation_id},
            )
            return {
                "response": f"I apologize, but I encountered an error: {exc}",
                "escalate": False,
                "rag_context_used": False,
                "rag_media_url": None,
                "rag_media_type": None,
            }
