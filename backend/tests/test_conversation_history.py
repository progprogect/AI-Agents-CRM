"""Tests for build_conversation_history_for_agent."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.message import Message, MessageChannel, MessageRole
from app.services.conversation_service import build_conversation_history_for_agent


def _msg(
    content: str,
    role: MessageRole,
    ts: datetime,
    message_id: str = "m1",
) -> Message:
    return Message(
        message_id=message_id,
        conversation_id="c1",
        agent_id="a1",
        role=role,
        content=content,
        channel=MessageChannel.WEB_CHAT,
        timestamp=ts,
    )


@pytest.mark.asyncio
async def test_build_history_dedup_last_user_turn():
    db = AsyncMock()
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    msgs = [
        _msg("hi", MessageRole.USER, t0, "1"),
        _msg("hello", MessageRole.USER, t0 + timedelta(minutes=1), "2"),
    ]
    db.list_messages = AsyncMock(return_value=list(reversed(msgs)))

    history = await build_conversation_history_for_agent(
        db, "c1", "hello", agent_context_reset_at=None
    )
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_build_history_excludes_messages_at_or_before_reset():
    db = AsyncMock()
    t_old = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_mid = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    t_new = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    reset_at = datetime(2025, 1, 1, 11, 30, 0, tzinfo=timezone.utc)

    msgs = [
        _msg("old", MessageRole.USER, t_old, "1"),
        _msg("mid", MessageRole.AGENT, t_mid, "2"),
        _msg("new", MessageRole.USER, t_new, "3"),
    ]
    db.list_messages = AsyncMock(return_value=list(reversed(msgs)))

    history = await build_conversation_history_for_agent(
        db, "c1", "new", agent_context_reset_at=reset_at
    )
    assert len(history) == 0
    assert history == []


@pytest.mark.asyncio
async def test_build_history_keeps_only_after_reset_then_dedup():
    db = AsyncMock()
    reset_at = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    t_after = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    msgs = [
        _msg("before", MessageRole.USER, datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc), "1"),
        _msg("current", MessageRole.USER, t_after, "2"),
    ]
    db.list_messages = AsyncMock(return_value=list(reversed(msgs)))

    history = await build_conversation_history_for_agent(
        db, "c1", "current", agent_context_reset_at=reset_at
    )
    assert history == []
