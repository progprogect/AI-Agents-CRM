"""handle_restart: MAX intro video + followup; Telegram video_note smoke."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.channel_binding import ChannelBinding, ChannelType
from app.services.bot_commands_service import handle_restart


def _max_binding() -> ChannelBinding:
    return ChannelBinding(
        binding_id="bind-max-1",
        agent_id="agent-1",
        channel_type=ChannelType.MAX,
        channel_account_id="max_bot",
    )


def _telegram_binding() -> ChannelBinding:
    return ChannelBinding(
        binding_id="bind-tg-1",
        agent_id="agent-1",
        channel_type=ChannelType.TELEGRAM,
        channel_account_id="tg_bot",
    )


def _mock_db(templates: dict) -> MagicMock:
    db = MagicMock()
    db.list_conversations = AsyncMock(return_value=[])
    db.create_conversation = AsyncMock(return_value=None)
    db.get_agent = AsyncMock(
        return_value={
            "config": {
                "prompts": {
                    "templates": templates,
                },
            },
        }
    )
    return db


@pytest.mark.anyio
async def test_handle_restart_max_sends_video_followup_and_welcome() -> None:
    templates = {
        "max_intro_video_url": "https://cdn.example.com/intro.mp4",
        "restart_welcome_followup": "Короткий текст после видео",
        "restart_welcome": "Добро пожаловать в чат!",
    }
    db = _mock_db(templates)
    calls: list[dict] = []

    async def capture_send(
        bot_token: str,
        chat_id: str,
        text: str,
        **kwargs: object,
    ) -> None:
        calls.append({"bot_token": bot_token, "chat_id": chat_id, "text": text, **kwargs})

    with (
        patch("app.services.bot_commands_service._send_telegram_message", new=AsyncMock(side_effect=capture_send)),
        patch("app.services.bot_commands_service.asyncio.sleep", new=AsyncMock()),
    ):
        await handle_restart(
            db=db,
            chat_id="user-1",
            binding=_max_binding(),
            bot_token="__generic_channel__",
        )

    assert len(calls) == 3
    assert calls[0]["media_url"] == "https://cdn.example.com/intro.mp4"
    assert calls[0]["media_type"] == "video"
    assert calls[0]["text"] == ""
    assert calls[1]["text"] == "Короткий текст после видео"
    assert calls[1].get("media_url") is None
    assert calls[2]["text"] == "Добро пожаловать в чат!"


@pytest.mark.anyio
async def test_handle_restart_max_skips_video_when_url_missing() -> None:
    templates = {"restart_welcome": "Только текст"}
    db = _mock_db(templates)
    calls: list[dict] = []

    async def capture_send(
        bot_token: str,
        chat_id: str,
        text: str,
        **kwargs: object,
    ) -> None:
        calls.append({"bot_token": bot_token, "chat_id": chat_id, "text": text, **kwargs})

    with patch(
        "app.services.bot_commands_service._send_telegram_message",
        new=AsyncMock(side_effect=capture_send),
    ):
        await handle_restart(
            db=db,
            chat_id="user-1",
            binding=_max_binding(),
            bot_token="__generic_channel__",
        )

    assert len(calls) == 1
    assert calls[0]["text"] == "Только текст"
    assert calls[0].get("media_url") is None


@pytest.mark.anyio
async def test_handle_restart_telegram_sends_video_note_not_max_url() -> None:
    templates = {
        "intro_video_note_file_id": "BQACAgIAAxkBAAI",
        "max_intro_video_url": "https://cdn.example.com/intro.mp4",
        "restart_welcome": "Привет из Telegram",
    }
    db = _mock_db(templates)
    text_calls: list[dict] = []

    async def capture_text_send(
        bot_token: str,
        chat_id: str,
        text: str,
        **kwargs: object,
    ) -> None:
        text_calls.append({"bot_token": bot_token, "chat_id": chat_id, "text": text, **kwargs})

    telegram_send = AsyncMock(return_value={"ok": True})

    with (
        patch("app.services.bot_commands_service._send_telegram_message", new=AsyncMock(side_effect=capture_text_send)),
        patch("app.services.bot_commands_service.asyncio.sleep", new=AsyncMock()),
        patch("app.services.bot_commands_service.TelegramService") as MockTelegramSvc,
        patch("app.services.bot_commands_service.ChannelBindingService"),
        patch("app.services.bot_commands_service.get_secrets_manager"),
        patch("app.services.bot_commands_service.get_settings"),
    ):
        MockTelegramSvc.return_value.send_message = telegram_send
        await handle_restart(
            db=db,
            chat_id="user-1",
            binding=_telegram_binding(),
            bot_token="tg-token",
        )

    telegram_send.assert_awaited_once()
    assert telegram_send.await_args.kwargs.get("media_type") == "video_note"
    assert len(text_calls) == 1
    assert text_calls[0]["text"] == "Привет из Telegram"
    for call in text_calls:
        assert call.get("media_url") != "https://cdn.example.com/intro.mp4"
