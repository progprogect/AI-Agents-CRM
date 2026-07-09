"""Deterministic quick-reply transitions (match_quick_reply) in agent_chain."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from langgraph.checkpoint.memory import MemorySaver

from app.chains.agent_chain import AgentChain, _graph_cache, _try_quick_reply_transition
from app.models.agent_config import AgentConfig, WorkflowStep

FIXTURE = Path(__file__).parent / "fixtures" / "day_lapu_vet_schedule_anchor_agent.json"

STEP_ANSWER = "step_1776689159495"
STEP_COMPLETE = "step_consult_complete"
STEP_PRIVACY = "step_privacy"


@pytest.fixture
def day_lapu_config() -> AgentConfig:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return AgentConfig.from_dict(data)


def _answer_step(cfg: AgentConfig) -> WorkflowStep:
    return next(s for s in cfg.workflow.steps if s.id == STEP_ANSWER)


def test_try_quick_reply_all_clear_advances(day_lapu_config: AgentConfig) -> None:
    step = _answer_step(day_lapu_config)
    step_map = {s.id: s for s in day_lapu_config.workflow.steps}
    state = {"user_message": "Все понятно", "conversation_id": "c1"}

    handled, next_id = _try_quick_reply_transition(state, step, step_map)
    assert handled is True
    assert next_id == STEP_COMPLETE


def test_try_quick_reply_stale_button_on_privacy(day_lapu_config: AgentConfig) -> None:
    step = next(s for s in day_lapu_config.workflow.steps if s.id == STEP_PRIVACY)
    step_map = {s.id: s for s in day_lapu_config.workflow.steps}
    state = {"user_message": "Все понятно", "conversation_id": "c1"}

    handled, next_id = _try_quick_reply_transition(state, step, step_map)
    assert handled is False
    assert next_id == STEP_PRIVACY


def test_try_quick_reply_more_questions_stays(day_lapu_config: AgentConfig) -> None:
    step = _answer_step(day_lapu_config)
    step_map = {s.id: s for s in day_lapu_config.workflow.steps}
    state = {"user_message": "Еще есть вопросы", "conversation_id": "c1"}

    handled, next_id = _try_quick_reply_transition(state, step, step_map)
    assert handled is True
    assert next_id == STEP_ANSWER


@pytest.mark.anyio
async def test_pre_transition_all_clear_without_llm_evaluator(day_lapu_config: AgentConfig) -> None:
    """«Все понятно» must advance via match_quick_reply without YES/NO evaluator calls."""
    _graph_cache.clear()

    eval_calls: list[str] = []

    async def llm_invoke(messages):
        content = messages[0].content if messages else ""
        if "Reply with exactly 'YES' or 'NO'" in content:
            eval_calls.append(content)
            return AIMessage(content="NO")
        return AIMessage(content="До встречи! 🐾")

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=llm_invoke)

    llm_factory = MagicMock()
    llm_factory.get_chat_model = AsyncMock(return_value=mock_llm)

    with patch(
        "app.storage.postgres_checkpointer.get_checkpointer",
        return_value=MemorySaver(),
    ):
        chain = AgentChain(agent_config=day_lapu_config, llm_factory=llm_factory)
        graph = chain._get_compiled_graph()

    rc = {
        "configurable": {
            "thread_id": "qr-test-all-clear",
            "llm": mock_llm,
            "moderation_service": None,
            "escalation_service": None,
            "rag_service": None,
            "is_reply_stale": None,
        }
    }

    await graph.aupdate_state(
        rc,
        {
            "conversation_id": "conv-qr-1",
            "agent_id": day_lapu_config.agent_id,
            "current_step_id": STEP_ANSWER,
            "step_history": [STEP_ANSWER],
            "collected": {},
            "messages": [],
        },
    )

    with patch(
        "app.chains.agent_chain._build_questionnaire_context_block",
        new_callable=AsyncMock,
        return_value="",
    ):
        final = await graph.ainvoke({"user_message": "Все понятно"}, config=rc)

    assert final.get("current_step_id") == STEP_COMPLETE
    assert final.get("result", {}).get("response")
    assert not any("Все понятно" in c and STEP_ANSWER in c for c in eval_calls)


@pytest.mark.anyio
async def test_pre_transition_more_questions_stays_on_answer_step(day_lapu_config: AgentConfig) -> None:
    _graph_cache.clear()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Задавай следующий вопрос 🐾"))

    llm_factory = MagicMock()
    llm_factory.get_chat_model = AsyncMock(return_value=mock_llm)

    with patch(
        "app.storage.postgres_checkpointer.get_checkpointer",
        return_value=MemorySaver(),
    ):
        chain = AgentChain(agent_config=day_lapu_config, llm_factory=llm_factory)
        graph = chain._get_compiled_graph()

    rc = {
        "configurable": {
            "thread_id": "qr-test-more-q",
            "llm": mock_llm,
            "moderation_service": None,
            "escalation_service": None,
            "rag_service": None,
            "is_reply_stale": None,
        }
    }

    await graph.aupdate_state(
        rc,
        {
            "conversation_id": "conv-qr-2",
            "agent_id": day_lapu_config.agent_id,
            "current_step_id": STEP_ANSWER,
            "step_history": [STEP_ANSWER],
            "collected": {},
            "messages": [],
        },
    )

    with patch(
        "app.chains.agent_chain._build_questionnaire_context_block",
        new_callable=AsyncMock,
        return_value="",
    ):
        final = await graph.ainvoke({"user_message": "Еще есть вопросы"}, config=rc)

    assert final.get("current_step_id") == STEP_ANSWER
    pending = final.get("pending_auto_schedules") or []
    assert not any(p["auto_step_id"] == "auto_recommendation_share" for p in pending)
