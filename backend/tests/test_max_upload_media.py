"""MAX media upload: POST /uploads and attachment.not.ready retry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.max_service import (
    MAX_API_BASE,
    MaxService,
    _is_max_attachment_not_ready_response,
)


def _make_service() -> MaxService:
    return MaxService(
        channel_binding_service=MagicMock(),
        db=MagicMock(),
        settings=MagicMock(),
    )


def test_is_max_attachment_not_ready_response() -> None:
    body = '{"code":"attachment.not.ready","message":"not processed"}'
    assert _is_max_attachment_not_ready_response(400, body) is True
    assert _is_max_attachment_not_ready_response(200, body) is False
    assert _is_max_attachment_not_ready_response(400, '{"code":"other"}') is False


@pytest.mark.anyio
async def test_upload_media_uses_post_not_get() -> None:
    svc = _make_service()
    upload_calls: list[str] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url.startswith(f"{MAX_API_BASE}/uploads"):
            upload_calls.append(url)
            return httpx.Response(
                200,
                json={"url": "https://vu.okcdn.ru/upload.do", "token": "tok-from-step1"},
                request=httpx.Request("POST", url),
            )
        if url == "https://vu.okcdn.ru/upload.do":
            return httpx.Response(
                200,
                json={"token": "tok-from-step2"},
                request=httpx.Request("POST", url),
            )
        raise AssertionError(f"unexpected post url: {url}")

    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url == "https://cdn.example.com/intro.mp4":
            return httpx.Response(
                200,
                content=b"fake-mp4-bytes",
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected get url: {url}")

    with (
        patch.object(httpx.AsyncClient, "post", new=fake_post),
        patch.object(httpx.AsyncClient, "get", new=fake_get),
    ):
        token = await svc._upload_media("bot-token", "https://cdn.example.com/intro.mp4", "video")

    assert token == "tok-from-step2"
    assert len(upload_calls) == 1
    assert upload_calls[0].startswith(f"{MAX_API_BASE}/uploads")


@pytest.mark.anyio
async def test_upload_media_returns_token_from_step1() -> None:
    svc = _make_service()

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url.startswith(f"{MAX_API_BASE}/uploads"):
            return httpx.Response(
                200,
                json={"url": "https://vu.okcdn.ru/upload.do", "token": "tok-from-step1"},
                request=httpx.Request("POST", url),
            )
        if url == "https://vu.okcdn.ru/upload.do":
            return httpx.Response(200, json={}, request=httpx.Request("POST", url))
        raise AssertionError(f"unexpected post url: {url}")

    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url == "https://cdn.example.com/intro.mp4":
            return httpx.Response(
                200,
                content=b"fake-mp4-bytes",
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected get url: {url}")

    with (
        patch.object(httpx.AsyncClient, "post", new=fake_post),
        patch.object(httpx.AsyncClient, "get", new=fake_get),
    ):
        token = await svc._upload_media("bot-token", "https://cdn.example.com/intro.mp4", "video")

    assert token == "tok-from-step1"


@pytest.mark.anyio
async def test_upload_media_returns_token_when_okcdn_body_empty() -> None:
    svc = _make_service()

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url.startswith(f"{MAX_API_BASE}/uploads"):
            return httpx.Response(
                200,
                json={"url": "https://omub.okcdn.ru/upload.do", "token": "tok-from-step1"},
                request=httpx.Request("POST", url),
            )
        if url == "https://omub.okcdn.ru/upload.do":
            return httpx.Response(200, text="", request=httpx.Request("POST", url))
        raise AssertionError(f"unexpected post url: {url}")

    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url == "https://cdn.example.com/intro.mp4":
            return httpx.Response(
                200,
                content=b"fake-mp4-bytes",
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected get url: {url}")

    with (
        patch.object(httpx.AsyncClient, "post", new=fake_post),
        patch.object(httpx.AsyncClient, "get", new=fake_get),
    ):
        token = await svc._upload_media("bot-token", "https://cdn.example.com/intro.mp4", "video")

    assert token == "tok-from-step1"


@pytest.mark.anyio
async def test_upload_media_raises_when_no_token_anywhere() -> None:
    svc = _make_service()

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url.startswith(f"{MAX_API_BASE}/uploads"):
            return httpx.Response(
                200,
                json={"url": "https://omub.okcdn.ru/upload.do"},
                request=httpx.Request("POST", url),
            )
        if url == "https://omub.okcdn.ru/upload.do":
            return httpx.Response(200, text="", request=httpx.Request("POST", url))
        raise AssertionError(f"unexpected post url: {url}")

    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url == "https://cdn.example.com/intro.mp4":
            return httpx.Response(
                200,
                content=b"fake-mp4-bytes",
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected get url: {url}")

    with (
        patch.object(httpx.AsyncClient, "post", new=fake_post),
        patch.object(httpx.AsyncClient, "get", new=fake_get),
    ):
        with pytest.raises(ValueError, match="no attachment token"):
            await svc._upload_media("bot-token", "https://cdn.example.com/intro.mp4", "video")


@pytest.mark.anyio
async def test_send_message_raw_retries_on_attachment_not_ready() -> None:
    svc = _make_service()
    message_calls = 0
    not_ready = '{"code":"attachment.not.ready","message":"not processed"}'

    async def fake_upload(access_token: str, media_url: str, upload_type: str, retries: int = 3) -> str:
        return "video-token-123"

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        nonlocal message_calls
        if url == f"{MAX_API_BASE}/messages":
            message_calls += 1
            if message_calls < 3:
                return httpx.Response(400, text=not_ready)
            return httpx.Response(200, json={"ok": True})
        raise AssertionError(f"unexpected url: {url}")

    with (
        patch.object(svc, "_upload_media", new=AsyncMock(side_effect=fake_upload)),
        patch.object(httpx.AsyncClient, "post", new=fake_post),
        patch("app.services.max_service.asyncio.sleep", new=AsyncMock()),
    ):
        await svc._send_message_raw(
            access_token="bot-token",
            chat_id=275779016,
            text="",
            media_url="https://cdn.example.com/intro.mp4",
            media_type="video",
        )

    assert message_calls == 3


@pytest.mark.anyio
async def test_send_message_raw_no_url_fallback_on_post_failure() -> None:
    svc = _make_service()
    media_url = "https://cdn.example.com/intro.mp4"
    sent_bodies: list[dict] = []

    async def fake_upload(access_token: str, media_url: str, upload_type: str, retries: int = 3) -> str:
        return "video-token-123"

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
        if url == f"{MAX_API_BASE}/messages":
            sent_bodies.append(kwargs.get("json") or {})
            return httpx.Response(500, text='{"code":"internal.error"}')
        raise AssertionError(f"unexpected url: {url}")

    with (
        patch.object(svc, "_upload_media", new=AsyncMock(side_effect=fake_upload)),
        patch.object(httpx.AsyncClient, "post", new=fake_post),
    ):
        await svc._send_message_raw(
            access_token="bot-token",
            chat_id=275779016,
            text="hello",
            media_url=media_url,
            media_type="video",
        )

    assert len(sent_bodies) == 1
    assert media_url not in (sent_bodies[0].get("text") or "")
    assert sent_bodies[0].get("attachments") == [
        {"type": "video", "payload": {"token": "video-token-123"}},
    ]