"""Сценарий «Дай Лапу»: конфиг с on_step_exit у авто-шага после «Дать ответ».

Проверяем ту же валидацию, что и PUT /api/v1/agents/{id}, и ожидаемый набор
pending_auto при переходе step_1776689159495 → step_1776714328598 (как в agent_chain).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import get_current_admin
from app.api.v1 import agents as agents_module
from app.api.v1 import chat as chat_module
from app.dependencies import CommonDependencies
from app.models.agent_config import AgentConfig
from app.models.conversation import Conversation

FIXTURE = Path(__file__).parent / "fixtures" / "day_lapu_vet_schedule_anchor_agent.json"


@pytest.fixture
def day_lapu_config() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_day_lapu_config_parses_like_api_validation(day_lapu_config: dict) -> None:
    """Тот же путь, что update_agent после merge: AgentConfig.from_dict."""
    cfg = AgentConfig.from_dict(day_lapu_config)
    assert cfg.agent_id == "day_lapu_tat_yana_vetirinarnyy_pomoshchnik_2"
    auto = cfg.workflow.auto_steps[0]
    assert auto.id == "auto_1776696721697"
    assert auto.source_id == "step_1776689159495"
    assert auto.schedule_anchor == "on_step_exit"
    assert auto.delay_seconds == 86400


def test_pending_auto_when_leaving_answer_step(day_lapu_config: dict) -> None:
    """При смене шага A→B: exit-авто по source_id==A и enter по source_id==B (как в agent_chain)."""
    cfg = AgentConfig.from_dict(day_lapu_config)
    wf = cfg.workflow
    step_id = "step_1776689159495"
    new_step_id = "step_1776714328598"

    enter_autos = [
        a.id
        for a in wf.auto_steps
        if a.source_id == new_step_id and a.schedule_anchor == "on_step_enter"
    ]
    exit_autos = [
        a.id
        for a in wf.auto_steps
        if a.source_id == step_id and a.schedule_anchor == "on_step_exit"
    ]

    assert set(enter_autos) == {"auto_after_share_followup", "auto_7day_reactivation"}
    assert exit_autos == ["auto_1776696721697"]

    pending_ids = enter_autos + exit_autos
    assert set(pending_ids) == {
        "auto_1776696721697",
        "auto_after_share_followup",
        "auto_7day_reactivation",
    }


def test_put_agent_endpoint_validates_fixture(day_lapu_config: dict) -> None:
    """HTTP PUT с тем же телом, что и слияние с пустым stored config — без реальной БД."""
    agent_id = day_lapu_config["agent_id"]

    app = FastAPI()
    app.include_router(agents_module.router, prefix="/api/v1/agents", tags=["agents"])

    async def override_admin() -> str:
        return "test"

    async def fake_create_agent(aid: str, config: dict) -> dict:
        return {
            "agent_id": aid,
            "config": config,
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2020-01-01T00:00:00Z",
            "is_active": True,
        }

    def override_common() -> CommonDependencies:
        mock_db = MagicMock()
        mock_db.get_agent = AsyncMock(return_value={"id": agent_id, "config": {}})
        mock_db.create_agent = AsyncMock(side_effect=fake_create_agent)
        mock_cache = MagicMock()
        settings = MagicMock()
        return CommonDependencies(config=settings, db=mock_db, cache=mock_cache)

    app.dependency_overrides[get_current_admin] = override_admin
    app.dependency_overrides[CommonDependencies] = override_common

    client = TestClient(app)
    r = client.put(f"/api/v1/agents/{agent_id}", json=day_lapu_config)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_id"] == agent_id
    assert body["config"]["workflow"]["auto_steps"][0]["schedule_anchor"] == "on_step_exit"


def test_chat_api_post_message_calls_schedule_auto_step_for_exit_anchor(day_lapu_config: dict) -> None:
    """POST /api/v1/chat/.../messages: после «ответа» граф отдаёт exit + enter авто — вызывается schedule_auto_step.

    Граф (LLM, чекпоинт) замокан; payload pending_auto как у agent_chain при
    переходе step_1776689159495 → step_1776714328598. Проверяем сквозной HTTP→AgentService→Redis.
    """
    agent_id = day_lapu_config["agent_id"]
    cfg = AgentConfig.from_dict(day_lapu_config)
    step_answer = "step_1776689159495"
    new_step_id = "step_1776714328598"

    enter_schedules = [
        {
            "auto_step_id": a.id,
            "delay_seconds": a.delay_seconds,
            "auto_step": a.model_dump(),
        }
        for a in cfg.workflow.auto_steps
        if a.source_id == new_step_id and a.schedule_anchor == "on_step_enter"
    ]
    exit_schedules = [
        {
            "auto_step_id": a.id,
            "delay_seconds": a.delay_seconds,
            "auto_step": a.model_dump(),
        }
        for a in cfg.workflow.auto_steps
        if a.source_id == step_answer and a.schedule_anchor == "on_step_exit"
    ]
    pending_schedules = enter_schedules + exit_schedules
    assert len(pending_schedules) == 3

    graph_return = {
        "response": "Спасибо, что обратились! Если что — я рядом 🐾",
        "cancel_all_auto_steps": True,
        "pending_auto_schedules": pending_schedules,
        "quick_replies": None,
    }

    conv_store: dict[str, Conversation] = {}

    app = FastAPI()
    app.include_router(chat_module.router, prefix="/api/v1/chat", tags=["chat"])

    def override_common() -> CommonDependencies:
        mock_db = MagicMock()

        async def _get_agent(aid: str):
            if aid == agent_id:
                return {"id": aid, "config": day_lapu_config}
            return None

        mock_db.get_agent = AsyncMock(side_effect=_get_agent)

        async def _create_conversation(conv: Conversation) -> None:
            conv_store[conv.conversation_id] = conv

        mock_db.create_conversation = AsyncMock(side_effect=_create_conversation)

        async def _get_conversation(cid: str):
            return conv_store.get(cid)

        mock_db.get_conversation = AsyncMock(side_effect=_get_conversation)
        mock_db.create_message = AsyncMock(return_value=None)
        mock_db.update_conversation = AsyncMock(return_value=True)
        mock_cache = MagicMock()
        settings = MagicMock()
        return CommonDependencies(config=settings, db=mock_db, cache=mock_cache)

    app.dependency_overrides[CommonDependencies] = override_common

    with (
        patch.object(chat_module, "get_settings", return_value=MagicMock(agent_reply_debounce_seconds=0)),
        patch.object(chat_module, "cancel_timer_trigger", new_callable=AsyncMock),
        patch.object(chat_module, "build_conversation_history_for_agent", new_callable=AsyncMock, return_value=[]),
        patch(
            "app.chains.agent_chain.AgentChain.generate_response",
            new_callable=AsyncMock,
            return_value=graph_return,
        ),
        patch(
            "app.services.agent_reply_coordinator.schedule_auto_step",
            new_callable=AsyncMock,
        ) as mock_schedule_auto,
        patch(
            "app.services.agent_reply_coordinator.cancel_auto_steps_for_workflow_transition",
            new_callable=AsyncMock,
        ) as mock_cancel_all,
    ):
        client = TestClient(app)
        cr = client.post("/api/v1/chat/conversations", json={"agent_id": agent_id})
        assert cr.status_code == 201, cr.text
        conversation_id = cr.json()["conversation_id"]

        r = client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "спасибо, вопрос решён"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["role"] == "agent"

    mock_cancel_all.assert_awaited_once()
    assert mock_schedule_auto.await_count == 3
    first_call_kwargs = mock_schedule_auto.await_args_list[0].kwargs
    auto_payload = first_call_kwargs["auto_step"]
    assert auto_payload.get("id") in (
        "auto_after_share_followup",
        "auto_7day_reactivation",
        "auto_1776696721697",
    )

    app.dependency_overrides.clear()
