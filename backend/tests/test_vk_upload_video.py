"""VK video upload and intro-video fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.channel_binding import ChannelType
from app.services.vk_service import VKService


def _vk_service() -> VKService:
    return VKService(channel_binding_service=MagicMock(), db=MagicMock())


def _mock_response(json_data: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.anyio
async def test_upload_video_returns_attachment() -> None:
    svc = _vk_service()
    video_bytes = b"fake-mp4-content"

    save_resp = _mock_response({
        "response": {
            "upload_url": "https://upload.vk.com/video",
            "owner_id": -123,
            "video_id": 456,
        },
    })
    download_resp = MagicMock()
    download_resp.content = video_bytes
    download_resp.raise_for_status = MagicMock()
    upload_resp = MagicMock()
    upload_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[save_resp, download_resp])
    mock_client.post = AsyncMock(return_value=upload_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.vk_service.httpx.AsyncClient", return_value=mock_client):
        attachment = await svc._upload_video(
            mock_client,
            "token",
            "https://cdn.example.com/intro.mp4",
            group_id=123,
        )

    assert attachment == "video-123_456"
    mock_client.post.assert_awaited_once()
    upload_call = mock_client.post.await_args
    assert "video_file" in upload_call.kwargs.get("files", {})


@pytest.mark.anyio
async def test_send_message_raw_intro_video_fallback_no_url_in_text() -> None:
    svc = _vk_service()
    svc._upload_and_get_attachment = AsyncMock(side_effect=RuntimeError("upload failed"))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_response({"response": 1}))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.vk_service.httpx.AsyncClient", return_value=mock_client):
        await svc._send_message_raw(
            access_token="token",
            peer_id=100,
            text="",
            media_url="https://cdn.example.com/intro.mp4",
            media_type="video",
            group_id=123,
        )

    mock_client.post.assert_not_awaited()


@pytest.mark.anyio
async def test_message_allow_dispatches_restart() -> None:
    svc = _vk_service()
    binding = MagicMock()
    binding.is_active = True
    binding.channel_type = ChannelType.VK
    binding.channel_account_id = "123"
    binding.agent_id = "agent-1"
    binding.binding_id = "bind-vk-1"
    binding.metadata = {}

    svc.channel_binding_service.get_binding = AsyncMock(return_value=binding)
    svc.channel_binding_service.get_access_token = AsyncMock(return_value="token")
    svc._make_command_send_fn = MagicMock(return_value=AsyncMock())

    with patch(
        "app.services.bot_commands_service.dispatch_command_generic",
        new=AsyncMock(),
    ) as mock_dispatch:
        result = await svc.handle_webhook_event(
            {"type": "message_allow", "object": {"user_id": 42}},
            "bind-vk-1",
        )

    assert result == "ok"
    mock_dispatch.assert_awaited_once()
    assert mock_dispatch.await_args.kwargs["command"] == "/restart"
    assert mock_dispatch.await_args.kwargs["chat_id"] == "42"
