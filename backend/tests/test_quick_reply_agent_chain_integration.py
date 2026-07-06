"""AgentChain integration: quick-reply transitions without LLM transition evaluator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

import app.chains.agent_chain as agent_chain_module
import app.storage.postgres_checkpointer as pg_ckpt
from app.chains.agent_chain import AgentChain
from app.models.agent_config import AgentConfig

FIXTURE = Path(__file__).parent / "fixtures" / "day_lapu_vet_schedule_anchor_agent.json"
ANSWER_STEP = "step_1776689159495"
COMPLETE_STEP = "step_consult_complete"


class TrackingLLM:
    """Mock LLM that records transition-eval calls and generation prompts."""

    def __init__(self) -> None:
        self.transition_eval_calls = 0
        self.last_invoke_blob = ""
        self.generation_blobs: list[str] = []

    def reset_counters(self) -> None:
        self.transition_eval_calls = 0
        self.last_invoke_blob = ""
        self.generation_blobs = []

    def _flatten(self, messages: list) -> str:
        parts: list[str] = []
        for m in messages:
            c = getattr(m, "content", "")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and "text" in b:
                        parts.append(str(b["text"]))
                    else:
                        parts.append(str(b))
        return "\n".join(parts)

    async def ainvoke(self, messages: list) -> AIMessage:
        blob = self._flatten(messages)
        self.last_invoke_blob = blob

        if "Evaluate whether the following condition is satisfied" in blob:
            self.transition_eval_calls += 1
            return AIMessage(content="NO")

        if "Extract the following fields" in blob and "Return ONLY a JSON object" in blob:
            return AIMessage(content=json.dumps({}, ensure_ascii=False))

        self.generation_blobs.append(blob)
        return AIMessage(content="Спасибо, что обратились! Если что — я рядом 🐾")


class _LLMFactory:
    def __init__(self, llm: TrackingLLM) -> None:
        self._llm = llm

    async def get_chat_model(self, agent_config: AgentConfig) -> TrackingLLM:
        return self._llm


@pytest.fixture(autouse=True)
def memory_checkpointer() -> None:
    pg_ckpt._checkpointer = MemorySaver()
    agent_chain_module._graph_cache.clear()
    yield
    agent_chain_module._graph_cache.clear()


@pytest.fixture
def day_lapu_config() -> AgentConfig:
    return AgentConfig.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


async def _seed_answer_step(
    chain: AgentChain,
    llm: TrackingLLM,
    conversation_id: str,
) -> None:
    graph = chain._get_compiled_graph()
    rc = RunnableConfig(
        configurable={
            "thread_id": conversation_id,
            "llm": llm,
            "moderation_service": None,
            "escalation_service": None,
            "rag_service": None,
            "is_reply_stale": None,
        }
    )
    await graph.aupdate_state(
        rc,
        {
            "user_message": "",
            "agent_id": chain.agent_config.agent_id,
            "conversation_id": conversation_id,
            "current_step_id": ANSWER_STEP,
            "step_history": ["step_privacy", "step_3", ANSWER_STEP],
            "collected": {
                "privacy_consent": "yes",
                "pet_name": "Мухтар",
                "pet_breed": "дворняга",
                "pet_age": "3",
            },
            "messages": [
                HumanMessage(content="собака чешется ухо"),
                AIMessage(content="Рекомендации по уходу за ухом."),
            ],
            "llm_response": "",
            "step_system_prompt": "",
        },
    )


@pytest.mark.anyio
async def test_vse_ponyatno_advances_without_llm_transition_eval(
    day_lapu_config: AgentConfig,
) -> None:
    llm = TrackingLLM()
    chain = AgentChain(day_lapu_config, llm_factory=_LLMFactory(llm))
    cid = "qr-int-vse-ponyatno"

    await _seed_answer_step(chain, llm, cid)
    llm.reset_counters()

    out = await chain.generate_response(
        "Все понятно",
        conversation_id=cid,
        moderation_service=None,
        escalation_service=None,
        rag_service=None,
    )

    assert llm.transition_eval_calls == 0
    pending = out.get("pending_auto_schedules") or []
    share_jobs = [p for p in pending if p.get("auto_step_id") == "auto_recommendation_share"]
    assert len(share_jobs) == 1
    share_auto = share_jobs[0].get("auto_step") or {}
    assert share_auto.get("source_id") == COMPLETE_STEP
    assert share_auto.get("schedule_anchor") == "on_step_enter"
    assert out.get("quick_replies") in (None, [])


@pytest.mark.anyio
async def test_eshche_est_voprosy_stays_without_pending_share(
    day_lapu_config: AgentConfig,
) -> None:
    llm = TrackingLLM()
    chain = AgentChain(day_lapu_config, llm_factory=_LLMFactory(llm))
    cid = "qr-int-eshche-voprosy"

    await _seed_answer_step(chain, llm, cid)
    llm.reset_counters()

    out = await chain.generate_response(
        "Еще есть вопросы",
        conversation_id=cid,
        moderation_service=None,
        escalation_service=None,
        rag_service=None,
    )

    # post_transition may still evaluate the «Все понятно» condition (NO) — pre_transition must not advance via LLM.
    pending = out.get("pending_auto_schedules") or []
    share_ids = {p.get("auto_step_id") for p in pending}
    assert "auto_recommendation_share" not in share_ids
    assert out.get("quick_replies") == ["Все понятно", "Еще есть вопросы"]


@pytest.mark.anyio
async def test_more_questions_injects_hint_in_step_prompt(
    day_lapu_config: AgentConfig,
) -> None:
    llm = TrackingLLM()
    chain = AgentChain(day_lapu_config, llm_factory=_LLMFactory(llm))
    cid = "qr-int-hint"

    await _seed_answer_step(chain, llm, cid)
    llm.reset_counters()

    await chain.generate_response(
        "Еще есть вопросы",
        conversation_id=cid,
        moderation_service=None,
        escalation_service=None,
        rag_service=None,
    )

    assert llm.generation_blobs, "expected at least one main LLM generation call"
    prompt_blob = llm.generation_blobs[0]
    assert "не завершай консультацию" in prompt_blob
    assert "Еще есть вопросы" in prompt_blob
