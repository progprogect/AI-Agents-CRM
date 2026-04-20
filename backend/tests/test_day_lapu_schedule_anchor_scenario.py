"""Сценарий «Дай Лапу»: конфиг с on_step_exit у авто-шага после «Дать ответ».

Проверяем ту же валидацию, что и PUT /api/v1/agents/{id}, и ожидаемый набор
pending_auto при переходе step_1776689159495 → step_1776709554108 (как в agent_chain).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import get_current_admin
from app.api.v1 import agents as agents_module
from app.dependencies import CommonDependencies
from app.models.agent_config import AgentConfig

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
    assert auto.delay_seconds == 3600


def test_pending_auto_when_leaving_answer_step(day_lapu_config: dict) -> None:
    """При смене шага A→B: exit-авто по source_id==A и enter по source_id==B (как в agent_chain)."""
    cfg = AgentConfig.from_dict(day_lapu_config)
    wf = cfg.workflow
    step_id = "step_1776689159495"
    new_step_id = "step_1776709554108"

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

    assert enter_autos == []
    assert exit_autos == ["auto_1776696721697"]

    pending_ids = enter_autos + exit_autos
    assert pending_ids == ["auto_1776696721697"]


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
