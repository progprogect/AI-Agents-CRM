"""Speech-to-text service using OpenAI gpt-4o-mini-transcribe.

Cost: $0.003/min (2× cheaper than Whisper-1 / gpt-4o-transcribe at $0.006/min).
Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg.
Telegram voice uses ``.oga`` on disk; we rename to ``.ogg`` for the API (same bytes).
File size limit: 25 MB per request.

Usage:
    from app.services.stt_service import transcribe_from_url, STTError
    try:
        text = await transcribe_from_url(url, language="ru")
    except STTError as exc:
        logger.warning("STT failed: %s", exc)
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 24 * 1024 * 1024  # 24 MB — stays under 25 MB API limit
STT_MODEL = "gpt-4o-mini-transcribe"


class STTError(Exception):
    """Raised when speech-to-text transcription fails."""


async def transcribe_bytes(
    audio_bytes: bytes,
    filename: str = "voice.webm",
    language: Optional[str] = None,
) -> str:
    """Transcribe audio from raw bytes (web chat MediaRecorder upload).

    Args:
        audio_bytes: Raw audio data (webm, ogg, mp4, etc.)
        filename: Filename with extension used for MIME type detection.
        language: BCP-47 language code hint, e.g. ``"ru"`` or ``"en"``.

    Returns:
        Transcript string (may be empty if audio is silent/unintelligible).

    Raises:
        STTError: On API error or missing API key.
    """
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise STTError(
            f"Audio exceeds size limit ({MAX_AUDIO_BYTES // (1024 * 1024)} MB)"
        )
    transcript = await _call_openai_transcription(audio_bytes, filename, language)
    logger.info(
        "STT transcribed %d bytes → %d chars (model=%s language=%s filename=%s)",
        len(audio_bytes),
        len(transcript),
        STT_MODEL,
        language or "auto",
        filename,
    )
    return transcript


async def transcribe_from_url(
    url: str,
    language: Optional[str] = None,
    max_bytes: int = MAX_AUDIO_BYTES,
) -> str:
    """Download audio from *url* and return the transcript text.

    Args:
        url: Publicly accessible audio URL (Telegram getFile URL, Cloudinary, etc.)
        language: BCP-47 language code hint, e.g. ``"ru"`` or ``"en"``.
            When None the model auto-detects the language.
        max_bytes: Maximum audio size to download.  Files larger than this are
            rejected without calling the API to avoid unexpectedly large charges.

    Returns:
        Transcript string (may be empty string if audio is silent/unintelligible).

    Raises:
        STTError: On download failure, size limit exceeded, or API error.
    """
    # --- Download audio ---
    audio_bytes = await _download_audio(url, max_bytes)

    # --- Detect filename hint from URL for MIME sniffing ---
    filename = _filename_from_url(url)

    # --- Call OpenAI Transcription API ---
    transcript = await _call_openai_transcription(audio_bytes, filename, language)
    logger.info(
        "STT transcribed %d bytes → %d chars (model=%s language=%s)",
        len(audio_bytes),
        len(transcript),
        STT_MODEL,
        language or "auto",
    )
    return transcript


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _download_audio(url: str, max_bytes: int) -> bytes:
    """Stream-download audio from *url* up to *max_bytes*."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > max_bytes:
                        raise STTError(
                            f"Audio file exceeds size limit ({max_bytes // (1024 * 1024)} MB): {url}"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)
    except STTError:
        raise
    except Exception as exc:
        raise STTError(f"Failed to download audio from {url}: {exc}") from exc


def _filename_from_url(url: str) -> str:
    """Extract a filename with extension from URL, fallback to voice.ogg."""
    try:
        path = url.split("?")[0].rstrip("/")
        name = path.split("/")[-1]
        if "." in name:
            return name
    except Exception:
        pass
    return "voice.ogg"


def _normalize_filename_for_openai_transcription(filename: str) -> str:
    """OpenAI /v1/audio/transcriptions rejects ``.oga`` (Telegram voice); use ``.ogg``."""
    if "." not in filename:
        return filename
    base, ext = filename.rsplit(".", 1)
    if ext.lower() == "oga":
        return f"{base}.ogg"
    return filename


async def _call_openai_transcription(
    audio_bytes: bytes,
    filename: str,
    language: Optional[str],
) -> str:
    """Send audio bytes to OpenAI Transcription API and return transcript."""
    api_key = await _get_openai_api_key()
    filename = _normalize_filename_for_openai_transcription(filename)

    # Determine content-type from filename extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "ogg"
    content_type_map = {
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "mp4": "audio/mp4",
        "m4a": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "mpga": "audio/mpeg",
        "mpeg": "audio/mpeg",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    data = {"model": STT_MODEL}
    if language:
        data["language"] = language

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files={"file": (filename, io.BytesIO(audio_bytes), content_type)},
            )
            response.raise_for_status()
            result = response.json()
            return (result.get("text") or "").strip()
    except httpx.HTTPStatusError as exc:
        raise STTError(
            f"OpenAI Transcription API error {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except Exception as exc:
        raise STTError(f"OpenAI Transcription API call failed: {exc}") from exc


async def _get_openai_api_key() -> str:
    """Retrieve the OpenAI API key using the same mechanism as the rest of the project."""
    try:
        from app.storage.resolver import get_secrets_manager
        sm = get_secrets_manager()
        return await sm.get_openai_api_key()
    except Exception as exc:
        raise STTError(f"Failed to retrieve OpenAI API key: {exc}") from exc
