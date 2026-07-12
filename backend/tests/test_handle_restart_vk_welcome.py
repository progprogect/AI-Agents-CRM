"""handle_restart: VK intro video + followup; Telegram file_id not used for VK."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.channel_binding import ChannelBinding, ChannelType
from app.services.bot_commands_service import handle_restart


def _vk_binding() -> ChannelBinding:
    return ChannelBinding(
        binding_id="bind-vk-1",
        agent_id="agent-1",
        channel_type=ChannelType.VK,
        channel_account_id="123456789",
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
async def test_handle_restart_vk_sends_video_followup_and_welcome() -> None:
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
            binding=_vk_binding(),
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
async def test_handle_restart_vk_skips_video_when_url_missing() -> None:
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
            binding=_vk_binding(),
            bot_token="__generic_channel__",
        )

    assert len(calls) == 1
    assert calls[0]["text"] == "Только текст"
    assert calls[0].get("media_url") is None


@pytest.mark.anyio
async def test_handle_restart_vk_uses_max_url_not_telegram_file_id() -> None:
    templates = {
        "intro_video_note_file_id": "BQACAgIAAxkBAAI",
        "max_intro_video_url": "https://cdn.example.com/intro.mp4",
        "restart_welcome": "Привет из VK",
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
            binding=_vk_binding(),
            bot_token="__generic_channel__",
        )

    assert len(calls) == 2
    assert calls[0]["media_url"] == "https://cdn.example.com/intro.mp4"
    assert calls[0]["media_type"] == "video"
    assert calls[1]["text"] == "Привет из VK"
    for call in calls:
        assert call.get("media_type") != "video_note"
