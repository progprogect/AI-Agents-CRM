"""MAX bot_started: use payload.chat_id, not user.user_id."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.max_service import MaxService

_DIALOG_CHAT_ID = 12345678901
_USER_ID = 357800218


def _make_service() -> MaxService:
    return MaxService(channel_binding_service=MagicMock(), db=MagicMock())


def _bot_started_payload(*, chat_id: int | None = _DIALOG_CHAT_ID) -> dict:
    payload: dict = {
        "update_type": "bot_started",
        "user": {"user_id": _USER_ID, "name": "Test"},
    }
    if chat_id is not None:
        payload["chat_id"] = chat_id
    return payload


@pytest.mark.anyio
async def test_handle_bot_started_uses_payload_chat_id_not_user_id() -> None:
    svc = _make_service()
    binding = MagicMock(binding_id="bind-1", agent_id="agent-1")
    binding_id = "bind-1"

    svc.channel_binding_service.get_access_token = AsyncMock(return_value="bot-token")

    dispatch_calls: list[dict] = []

    async def _capture_dispatch(**kwargs: object) -> bool:
        dispatch_calls.append(kwargs)
        return True

    with patch(
        "app.services.bot_commands_service.dispatch_command_generic",
        new=AsyncMock(side_effect=_capture_dispatch),
    ):
        await svc._handle_bot_started(_bot_started_payload(), binding, binding_id)

    assert len(dispatch_calls) == 1
    assert dispatch_calls[0]["chat_id"] == str(_DIALOG_CHAT_ID)
    assert dispatch_calls[0]["command"] == "/restart"

    send_fn = dispatch_calls[0]["send_fn"]
    send_raw_calls: list[int] = []

    async def _capture_send_raw(
        access_token: str,
        chat_id: int,
        text: str,
        **kwargs: object,
    ) -> None:
        send_raw_calls.append(chat_id)

    with patch.object(svc, "_send_message_raw", new=AsyncMock(side_effect=_capture_send_raw)):
        await send_fn("hello")

    assert send_raw_calls == [_DIALOG_CHAT_ID]


@pytest.mark.anyio
async def test_handle_bot_started_falls_back_to_user_id_when_chat_id_missing() -> None:
    svc = _make_service()
    binding = MagicMock(binding_id="bind-1")
    binding_id = "bind-1"

    svc.channel_binding_service.get_access_token = AsyncMock(return_value="bot-token")

    with patch(
        "app.services.bot_commands_service.dispatch_command_generic",
        new=AsyncMock(return_value=True),
    ) as mock_dispatch:
        await svc._handle_bot_started(_bot_started_payload(chat_id=None), binding, binding_id)

    mock_dispatch.assert_awaited_once()
    assert mock_dispatch.await_args.kwargs["chat_id"] == str(_USER_ID)


@pytest.mark.anyio
async def test_handle_bot_started_skips_when_no_ids() -> None:
    svc = _make_service()
    binding = MagicMock(binding_id="bind-1")
    binding_id = "bind-1"

    with patch(
        "app.services.bot_commands_service.dispatch_command_generic",
        new=AsyncMock(return_value=True),
    ) as mock_dispatch:
        await svc._handle_bot_started({"update_type": "bot_started", "user": {}}, binding, binding_id)

    mock_dispatch.assert_not_awaited()
