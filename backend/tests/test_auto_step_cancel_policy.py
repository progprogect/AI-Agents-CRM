"""Tests for cancel_on_workflow_step_change and selective Redis cancellation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.agent_config import WorkflowAutoStep, WorkflowConfig, WorkflowStep
from app.services.agent_reply_coordinator import (
    KEY_AUTO_DUE,
    KEY_AUTO_IDX,
    KEY_AUTO_PAY,
    KEY_AUTO_ONCE_PREFIX,
    _payload_cancel_on_workflow_step_change,
    cancel_all_auto_steps,
    cancel_auto_steps_for_workflow_transition,
)


def test_payload_cancel_defaults_true_when_missing_or_invalid() -> None:
    assert _payload_cancel_on_workflow_step_change(None) is True
    assert _payload_cancel_on_workflow_step_change("") is True
    assert _payload_cancel_on_workflow_step_change("not json") is True
    assert _payload_cancel_on_workflow_step_change(json.dumps([])) is True
    assert _payload_cancel_on_workflow_step_change(json.dumps({"id": "x"})) is True
    assert _payload_cancel_on_workflow_step_change(json.dumps({"cancel_on_workflow_step_change": True})) is True
    assert _payload_cancel_on_workflow_step_change(json.dumps({"cancel_on_workflow_step_change": False})) is False
    assert _payload_cancel_on_workflow_step_change(
        json.dumps({"cancel_on_workflow_step_change": None})
    ) is True


def test_workflow_auto_step_default_cancel_on_workflow_step_change() -> None:
    wf = WorkflowConfig(
        enabled=True,
        start_step_id="s1",
        steps=[
            WorkflowStep(
                id="s1",
                name="S",
                instructions="i",
                collect=[],
                required=False,
                transitions=[],
                timer_trigger=None,
                quick_replies=[],
            ),
        ],
        auto_steps=[
            WorkflowAutoStep(
                id="a1",
                name="A",
                source_id="s1",
                delay_seconds=10,
                action_type="static",
                message_template="m",
            ),
        ],
    )
    assert wf.auto_steps[0].cancel_on_workflow_step_change is True
    dumped = wf.auto_steps[0].model_dump()
    assert dumped.get("cancel_on_workflow_step_change") is True


@pytest.mark.asyncio
async def test_cancel_auto_steps_for_workflow_transition_selective() -> None:
    conv = "conv-1"
    m_ephemeral = f"{conv}:ephemeral"
    m_sticky = f"{conv}:sticky"
    idx_key = f"{KEY_AUTO_IDX}{conv}"

    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    redis.smembers = AsyncMock(return_value={m_ephemeral, m_sticky})

    async def _get(key: str) -> str | None:
        if key == f"{KEY_AUTO_PAY}{m_sticky}":
            return json.dumps({"id": "sticky", "cancel_on_workflow_step_change": False})
        if key == f"{KEY_AUTO_PAY}{m_ephemeral}":
            return json.dumps({"id": "ephemeral"})
        return None

    redis.get = AsyncMock(side_effect=_get)
    redis.zrem = AsyncMock()
    redis.delete = AsyncMock()
    redis.srem = AsyncMock()

    with patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis):
        await cancel_auto_steps_for_workflow_transition(conv)

    redis.zrem.assert_called_once_with(KEY_AUTO_DUE, m_ephemeral)
    redis.delete.assert_called_once_with(f"{KEY_AUTO_PAY}{m_ephemeral}")
    redis.srem.assert_called_once_with(idx_key, m_ephemeral)


@pytest.mark.asyncio
async def test_cancel_all_auto_steps_removes_all_members() -> None:
    conv = "conv-2"
    members = {f"{conv}:a", f"{conv}:b"}
    idx_key = f"{KEY_AUTO_IDX}{conv}"

    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    redis.smembers = AsyncMock(return_value=members)
    redis.zrem = AsyncMock()
    redis.delete = AsyncMock()
    redis.srem = AsyncMock()

    with patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis):
        await cancel_all_auto_steps(conv)

    zargs = redis.zrem.call_args[0]
    assert zargs[0] == KEY_AUTO_DUE
    assert set(zargs[1:]) == members
    assert redis.delete.await_count == 4
    redis.delete.assert_any_call(f"{KEY_AUTO_PAY}{conv}:a")
    redis.delete.assert_any_call(f"{KEY_AUTO_PAY}{conv}:b")
    redis.delete.assert_any_call(idx_key)
    redis.delete.assert_any_call(f"{KEY_AUTO_ONCE_PREFIX}{conv}")
