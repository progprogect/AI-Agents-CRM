"""MAX inline keyboard conv hint and stale-session callback handling."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.conversation import Conversation, ConversationStatus
from app.models.message import MessageChannel
from app.services.max_service import MaxService, _build_max_inline_keyboard
from app.utils.datetime_utils import utc_now


def test_build_max_inline_keyboard_includes_conv_hint() -> None:
    kb = _build_max_inline_keyboard(
        ["Все понятно", "Еще есть вопросы"],
        conversation_id="abcd1234-5678-90ab-cdef-1234567890ab",
    )
    assert kb is not None
    payload_raw = kb["payload"]["buttons"][0][0]["payload"]
    payload = json.loads(payload_raw)
    assert payload["cmd"] == "reply"
    assert payload["text"] == "Все понятно"
    assert payload["conv"] == "abcd1234"


def test_build_max_inline_keyboard_without_conversation_id_omits_conv() -> None:
    kb = _build_max_inline_keyboard(["Все понятно"])
    assert kb is not None
    payload = json.loads(kb["payload"]["buttons"][0][0]["payload"])
    assert "conv" not in payload


def _make_service() -> MaxService:
    return MaxService(
        channel_binding_service=MagicMock(),
        db=MagicMock(),
        settings=MagicMock(),
    )


def _callback_payload(conv: str | None, text: str = "Все понятно") -> dict:
    body: dict = {"cmd": "reply", "text": text}
    if conv is not None:
        body["conv"] = conv
    return {
        "callback": {
            "callback_id": "cb-1",
            "payload": json.dumps(body, ensure_ascii=False),
            "user": {"user_id": 12345},
        },
    }


@pytest.mark.anyio
async def test_stale_conv_sends_restart_message_and_skips_pipeline() -> None:
    svc = _make_service()
    binding = SimpleNamespace(agent_id="agent-1", binding_id="bind-1")

    svc.channel_binding_service.get_access_token = AsyncMock(return_value="token")
    svc._answer_callback = AsyncMock()
    svc._get_active_conversation = AsyncMock(
        return_value=Conversation(
            conversation_id="ffff9999-0000-0000-0000-000000000001",
            agent_id="agent-1",
            channel=MessageChannel.MAX,
            external_user_id="12345",
            status=ConversationStatus.AI_ACTIVE,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    svc._send_text = AsyncMock()
    svc._handle_message_created = AsyncMock()

    await svc._handle_message_callback(
        _callback_payload("abcd1234"),
        binding,
        "bind-1",
    )

    svc._send_text.assert_awaited_once()
    assert "устарела" in svc._send_text.await_args.args[2].lower()
    svc._handle_message_created.assert_not_awaited()


@pytest.mark.anyio
async def test_matching_conv_forwards_to_message_pipeline() -> None:
    svc = _make_service()
    binding = SimpleNamespace(agent_id="agent-1", binding_id="bind-1")
    active_id = "abcd1234-5678-90ab-cdef-1234567890ab"

    svc.channel_binding_service.get_access_token = AsyncMock(return_value="token")
    svc._answer_callback = AsyncMock()
    svc._get_active_conversation = AsyncMock(
        return_value=Conversation(
            conversation_id=active_id,
            agent_id="agent-1",
            channel=MessageChannel.MAX,
            external_user_id="12345",
            status=ConversationStatus.AI_ACTIVE,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    svc._send_text = AsyncMock()
    svc._handle_message_created = AsyncMock()

    await svc._handle_message_callback(
        _callback_payload("abcd1234", text="Все понятно"),
        binding,
        "bind-1",
    )

    svc._send_text.assert_not_awaited()
    svc._handle_message_created.assert_awaited_once()
    synthetic = svc._handle_message_created.await_args.args[0]
    assert synthetic["message"]["body"]["text"] == "Все понятно"


@pytest.mark.anyio
async def test_legacy_callback_without_conv_still_forwards() -> None:
    svc = _make_service()
    binding = SimpleNamespace(agent_id="agent-1", binding_id="bind-1")

    svc.channel_binding_service.get_access_token = AsyncMock(return_value="token")
    svc._answer_callback = AsyncMock()
    svc._get_active_conversation = AsyncMock(return_value=None)
    svc._send_text = AsyncMock()
    svc._handle_message_created = AsyncMock()

    await svc._handle_message_callback(
        _callback_payload(None, text="Все понятно"),
        binding,
        "bind-1",
    )

    svc._send_text.assert_not_awaited()
    svc._get_active_conversation.assert_not_awaited()
    svc._handle_message_created.assert_awaited_once()
