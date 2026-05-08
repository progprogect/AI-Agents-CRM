"""Tests for user reminder queue helpers."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.reminder_message_generator import _fallback_text
from app.services.reminder_wizard_service import WizardMode, WizardState
from app.services.telegram_reminder_flow import next_fire_once_1h
from app.services.user_reminder_scheduler import (
    KEY_USER_REMINDER_DUE,
    enqueue_user_reminder,
)
from app.utils.datetime_utils import utc_now


def test_fallback_text_includes_note() -> None:
    t = _fallback_text("vaccination", "Борис через месяц")
    assert "прививка" in t.lower() or "Прививка" in t
    assert "Борис" in t


@pytest.mark.asyncio
async def test_enqueue_user_reminder_zadd() -> None:
    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    redis.zadd = AsyncMock()

    dt = utc_now() + timedelta(hours=2)
    with patch(
        "app.services.user_reminder_scheduler.get_redis_client", return_value=redis
    ):
        await enqueue_user_reminder("rid-1", dt)

    redis.zadd.assert_awaited_once()
    args = redis.zadd.call_args[0]
    assert args[0] == KEY_USER_REMINDER_DUE
    assert "rid-1" in args[1]


def test_wizard_state_serializes_draft_fields() -> None:
    st = WizardState(
        binding_id="b1",
        external_user_id="u1",
        mode=WizardMode.NOTE,
        category="vaccination",
        schedule_kind="once",
        next_fire_iso="2026-05-10T10:00:00+00:00",
        pending_schedule_spec={"preset": "1h"},
    )
    d = st.to_dict()
    st2 = WizardState.from_dict("b1", "u1", d)
    assert st2.next_fire_iso == st.next_fire_iso
    assert st2.pending_schedule_spec == {"preset": "1h"}


def test_next_fire_once_1h_future() -> None:
    t = next_fire_once_1h()
    assert t > utc_now()
