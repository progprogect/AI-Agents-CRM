"""Deterministic quick-reply workflow transitions (match_quick_reply)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.chains.agent_chain import _try_quick_reply_transition
from app.models.agent_config import AgentConfig, WorkflowTransition
from app.services.agent_reply_coordinator import (
    KEY_AUTO_DUE,
    KEY_AUTO_IDX,
    KEY_AUTO_PAY,
    _payload_cancel_on_workflow_step_change,
    cancel_auto_steps_for_workflow_transition,
)

FIXTURE = Path(__file__).parent / "fixtures" / "day_lapu_vet_schedule_anchor_agent.json"


@pytest.fixture
def day_lapu_config() -> AgentConfig:
    return AgentConfig.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _step_map(cfg: AgentConfig) -> dict:
    return {s.id: s for s in cfg.workflow.steps}


def _state(step_id: str, user_message: str) -> dict:
    return {
        "user_message": user_message,
        "current_step_id": step_id,
        "conversation_id": "test-conversation-id",
        "messages": [],
        "collected": {},
    }


def test_vse_ponyatno_on_answer_step_transitions_to_consult_complete(day_lapu_config: AgentConfig) -> None:
    step_map = _step_map(day_lapu_config)
    step = step_map["step_1776689159495"]
    result = _try_quick_reply_transition(_state(step.id, "Все понятно"), step, step_map)
    assert result == "step_consult_complete"


def test_vse_ponyatno_on_privacy_step_does_not_transition(day_lapu_config: AgentConfig) -> None:
    step_map = _step_map(day_lapu_config)
    step = step_map["step_privacy"]
    result = _try_quick_reply_transition(_state(step.id, "Все понятно"), step, step_map)
    assert result is None


def test_eshche_est_voprosy_stays_on_answer_step(day_lapu_config: AgentConfig) -> None:
    step_map = _step_map(day_lapu_config)
    step = step_map["step_1776689159495"]
    result = _try_quick_reply_transition(_state(step.id, "Еще есть вопросы"), step, step_map)
    assert result == "step_1776689159495"


def test_share_not_scheduled_when_staying_on_answer_step(day_lapu_config: AgentConfig) -> None:
    """Ordinary turn on «Дать ответ» (no step change) must not schedule share auto."""
    wf = day_lapu_config.workflow
    step_id = "step_1776689159495"
    enter_autos = [
        a.id
        for a in wf.auto_steps
        if a.source_id == step_id and a.schedule_anchor == "on_step_enter"
    ]
    exit_autos = [
        a.id
        for a in wf.auto_steps
        if a.source_id == step_id and a.schedule_anchor == "on_step_exit"
    ]
    assert enter_autos == []
    assert exit_autos == []


def test_share_scheduled_on_enter_consult_complete(day_lapu_config: AgentConfig) -> None:
    wf = day_lapu_config.workflow
    new_step_id = "step_consult_complete"
    enter_autos = [
        a.id
        for a in wf.auto_steps
        if a.source_id == new_step_id and a.schedule_anchor == "on_step_enter"
    ]
    assert enter_autos == ["auto_recommendation_share"]


def test_workflow_transition_match_quick_reply_roundtrip() -> None:
    t = WorkflowTransition(
        condition="Пользователь нажал «Все понятно»",
        next_step_id="step_consult_complete",
        match_quick_reply="Все понятно",
    )
    dumped = t.model_dump()
    assert dumped["match_quick_reply"] == "Все понятно"


def test_fixture_answer_step_has_match_quick_reply(day_lapu_config: AgentConfig) -> None:
    step = next(s for s in day_lapu_config.workflow.steps if s.id == "step_1776689159495")
    assert step.transitions[0].match_quick_reply == "Все понятно"


def test_share_auto_payload_cancel_on_step_change(day_lapu_config: AgentConfig) -> None:
    share = next(a for a in day_lapu_config.workflow.auto_steps if a.id == "auto_recommendation_share")
    assert share.cancel_on_workflow_step_change is True
    assert _payload_cancel_on_workflow_step_change(json.dumps(share.model_dump())) is True


@pytest.mark.anyio
async def test_day_lapu_share_auto_removed_on_workflow_transition(day_lapu_config: AgentConfig) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    conv = "conv-share-cancel"
    member = f"{conv}:auto_recommendation_share"
    share = next(a for a in day_lapu_config.workflow.auto_steps if a.id == "auto_recommendation_share")
    idx_key = f"{KEY_AUTO_IDX}{conv}"

    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    redis.smembers = AsyncMock(return_value={member})

    async def _get(key: str) -> str | None:
        if key == f"{KEY_AUTO_PAY}{member}":
            return json.dumps(share.model_dump())
        return None

    redis.get = AsyncMock(side_effect=_get)
    redis.zrem = AsyncMock()
    redis.delete = AsyncMock()
    redis.srem = AsyncMock()

    with patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis):
        await cancel_auto_steps_for_workflow_transition(conv)

    redis.zrem.assert_called_once_with(KEY_AUTO_DUE, member)
    redis.delete.assert_called_once_with(f"{KEY_AUTO_PAY}{member}")
    redis.srem.assert_called_once_with(idx_key, member)
