"""MAX quick-reply button transport: type message + legacy callback fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.max_service import (
    MaxService,
    _build_max_inline_keyboard,
    _resolve_callback_button_text,
)


def test_build_max_inline_keyboard_uses_message_type() -> None:
    labels = ["Все понятно", "Еще есть вопросы"]
    kb = _build_max_inline_keyboard(labels)
    assert kb is not None
    buttons = kb["payload"]["buttons"]
    flat = [btn for row in buttons for btn in row]
    assert len(flat) == 2
    for btn, label in zip(flat, labels):
        assert btn["type"] == "message"
        assert btn["text"] == label
        assert btn["payload"] == label


def test_resolve_callback_button_text_json_reply() -> None:
    raw = json.dumps({"cmd": "reply", "text": "Все понятно"}, ensure_ascii=False)
    assert _resolve_callback_button_text(raw, {}) == "Все понятно"


def test_resolve_callback_button_text_plain_string() -> None:
    assert _resolve_callback_button_text("Еще есть вопросы", {}) == "Еще есть вопросы"


def test_resolve_callback_button_text_from_keyboard_attachment() -> None:
    message_data = {
        "body": {
            "attachments": [
                {
                    "type": "inline_keyboard",
                    "payload": {
                        "buttons": [[
                            {
                                "type": "callback",
                                "text": "Все понятно",
                                "payload": "opaque-payload-id",
                            }
                        ]]
                    },
                }
            ]
        }
    }
    assert _resolve_callback_button_text("opaque-payload-id", message_data) == "Все понятно"


@pytest.mark.anyio
async def test_handle_message_callback_legacy_reply_uses_recipient_chat_id() -> None:
    svc = MaxService(channel_binding_service=MagicMock(), db=MagicMock())
    binding = MagicMock(agent_id="agent-1", is_active=True)
    binding_id = "bind-1"

    svc.channel_binding_service.get_access_token = AsyncMock(return_value="token")
    svc._answer_callback = AsyncMock()

    captured: dict = {}

    async def _capture_created(payload, _binding, _binding_id):
        captured["payload"] = payload

    svc._handle_message_created = _capture_created

    cb_payload = json.dumps({"cmd": "reply", "text": "Все понятно"}, ensure_ascii=False)
    webhook = {
        "callback": {
            "callback_id": "cb-1",
            "payload": cb_payload,
            "user": {"user_id": 99999},
        },
        "message": {
            "recipient": {"chat_id": 12345, "chat_type": "dialog", "user_id": 12345},
            "timestamp": 0,
        },
    }

    await svc._handle_message_callback(webhook, binding, binding_id)

    assert "payload" in captured
    msg = captured["payload"]["message"]
    assert msg["recipient"]["chat_id"] == 12345
    assert msg["body"]["text"] == "Все понятно"
    assert msg["sender"]["user_id"] == 99999


@pytest.mark.anyio
async def test_handle_message_callback_plain_payload_invokes_pipeline() -> None:
    svc = MaxService(channel_binding_service=MagicMock(), db=MagicMock())
    binding = MagicMock(agent_id="agent-1")
    binding_id = "bind-1"

    svc.channel_binding_service.get_access_token = AsyncMock(return_value="token")
    svc._answer_callback = AsyncMock()

    with patch.object(svc, "_handle_message_created", new_callable=AsyncMock) as mock_created:
        webhook = {
            "callback": {
                "callback_id": "cb-2",
                "payload": "Еще есть вопросы",
                "user": {"user_id": 777},
            },
            "message": {
                "recipient": {"chat_id": 555, "chat_type": "dialog"},
            },
        }
        await svc._handle_message_callback(webhook, binding, binding_id)

    mock_created.assert_awaited_once()
    synthetic = mock_created.await_args.args[0]
    assert synthetic["message"]["body"]["text"] == "Еще есть вопросы"
    assert synthetic["message"]["recipient"]["chat_id"] == 555
