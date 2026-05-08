"""Тесты флага once_per_conversation для автошагов (Redis SET + schedule guard)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent_reply_coordinator import (
    KEY_AUTO_ONCE_PREFIX,
    cancel_all_auto_steps,
    schedule_auto_step,
)


@pytest.mark.asyncio
async def test_schedule_skips_when_once_already_recorded() -> None:
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.sismember = AsyncMock(return_value=True)

    auto = {"id": "auto_share", "delay_seconds": 60, "once_per_conversation": True}

    with patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis):
        await schedule_auto_step("conv-a", auto, "cfg-hash", 999_000)

    redis.sismember.assert_awaited_once_with(f"{KEY_AUTO_ONCE_PREFIX}conv-a", "auto_share")
    redis.set.assert_not_called()
    redis.zadd.assert_not_called()
    redis.sadd.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_proceeds_when_not_yet_recorded() -> None:
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.sismember = AsyncMock(return_value=False)

    auto = {"id": "auto_share", "delay_seconds": 60, "once_per_conversation": True}

    with patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis):
        await schedule_auto_step("conv-b", auto, "cfg-hash", 1_000_000)

    redis.zadd.assert_awaited()
    redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_schedule_proceeds_when_sismember_check_fails() -> None:
    """Fail-open: если проверка Redis упала — планируем как обычно."""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.sismember = AsyncMock(side_effect=RuntimeError("redis down"))

    auto = {"id": "auto_share", "delay_seconds": 60, "once_per_conversation": True}

    with patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis):
        await schedule_auto_step("conv-c", auto, "cfg-hash", 2_000_000)

    redis.zadd.assert_awaited()


@pytest.mark.asyncio
async def test_cancel_all_auto_steps_deletes_once_key() -> None:
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.smembers = AsyncMock(return_value={"conv-d:step1"})

    with patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis):
        await cancel_all_auto_steps("conv-d")

    deleted = [c.args[0] for c in redis.delete.await_args_list]
    assert f"{KEY_AUTO_ONCE_PREFIX}conv-d" in deleted
