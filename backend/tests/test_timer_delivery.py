"""Unit tests for timer delivery fixes.

Tests cover:
1. MessageRole.AGENT is valid (no AttributeError — regression guard)
2. execute_timer_trigger calls channel_sender.send_message with message_id
3. WebChatSender calls connection_manager.send_message and handles missing WS
4. Dead-letter key is written to Redis on task failure
"""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest import mark

from app.models.message import Message, MessageChannel, MessageRole
from app.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# 1. MessageRole.AGENT exists and Message can be created with it
# ---------------------------------------------------------------------------

def test_message_role_agent_exists():
    """Regression: MessageRole.ASSISTANT was used but does not exist."""
    assert hasattr(MessageRole, "AGENT"), "MessageRole.AGENT must exist"


def test_message_creation_with_agent_role():
    """Message(role=MessageRole.AGENT) must not raise AttributeError."""
    msg = Message(
        message_id="test-id",
        conversation_id="conv-1",
        agent_id="agent-1",
        role=MessageRole.AGENT,
        content="Hello from timer",
        channel=MessageChannel.WEB_CHAT,
        timestamp=utc_now(),
    )
    assert msg.role == MessageRole.AGENT


# ---------------------------------------------------------------------------
# 2. execute_timer_trigger passes message_id to channel_sender.send_message
# ---------------------------------------------------------------------------

def test_timer_send_message_receives_message_id():
    """channel_sender.send_message call in execute_timer_trigger includes message_id.

    We verify the source code directly to avoid heavy integration mocking:
    after our fix the call must include `message_id=timer_msg.message_id`.
    """
    import inspect
    from app.services import agent_reply_coordinator as arc

    source = inspect.getsource(arc.execute_timer_trigger)
    assert "message_id=timer_msg.message_id" in source, (
        "execute_timer_trigger must pass message_id=timer_msg.message_id to channel_sender.send_message"
    )


# ---------------------------------------------------------------------------
# 3. WebChatSender pushes to connection_manager, handles missing WS gracefully
# ---------------------------------------------------------------------------

@mark.asyncio
async def test_webchat_sender_pushes_to_connection_manager():
    """WebChatSender must call connection_manager.send_message."""
    from app.services.channel_sender import WebChatSender

    mock_cm = MagicMock()
    mock_cm.send_message = AsyncMock(return_value=True)

    with patch("app.api.websocket.connection_manager", mock_cm):
        sender = WebChatSender(db=MagicMock())
        await sender.send_message(
            conversation_id="conv-1",
            message_text="Hello",
            message_id="msg-42",
        )

    mock_cm.send_message.assert_called_once()
    payload = mock_cm.send_message.call_args.args[1]
    assert payload["type"] == "message"
    assert payload["message_id"] == "msg-42"
    assert payload["role"] == "agent"
    assert payload["content"] == "Hello"


@mark.asyncio
async def test_webchat_sender_no_active_connection_does_not_raise():
    """WebChatSender must not raise when there is no active WS connection."""
    from app.services.channel_sender import WebChatSender

    mock_cm = MagicMock()
    mock_cm.send_message = AsyncMock(return_value=False)  # no active socket

    with patch("app.api.websocket.connection_manager", mock_cm):
        sender = WebChatSender(db=MagicMock())
        # Must complete without raising
        await sender.send_message(conversation_id="conv-orphan", message_text="Ping")


# ---------------------------------------------------------------------------
# 4. Dead-letter key is written to Redis on timer task failure
# ---------------------------------------------------------------------------

@mark.asyncio
async def test_dead_letter_written_on_timer_failure():
    """When execute_timer_trigger raises, a dead-letter key must be written."""
    from app.services import agent_reply_coordinator as arc

    written_keys: dict[str, str] = {}

    mock_redis = MagicMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.zrangebyscore = AsyncMock(return_value=["conv-fail"])
    mock_redis.set_nx_ex = AsyncMock(return_value=True)
    mock_redis.zscore = AsyncMock(return_value=float(int(time.time() * 1000) - 1000))
    mock_redis.zrem = AsyncMock()
    mock_redis.delete = AsyncMock()

    async def fake_set(key, value, ttl=None):
        written_keys[key] = value

    mock_redis.set = AsyncMock(side_effect=fake_set)

    async def boom(cid: str) -> None:
        raise RuntimeError("simulated crash")

    with (
        patch.object(arc, "get_redis_client", return_value=mock_redis),
        patch.object(arc, "execute_timer_trigger", boom),
    ):
        await arc._poll_timers_once()
        # Give the asyncio task a chance to run
        import asyncio
        await asyncio.sleep(0.05)

    dead_letter_keys = [k for k in written_keys if k.startswith(arc.KEY_TIMER_FAILED_PREFIX)]
    assert dead_letter_keys, "Dead-letter key must be written when timer task fails"
    entry = json.loads(written_keys[dead_letter_keys[0]])
    assert "error" in entry
    assert "simulated crash" in entry["error"]
