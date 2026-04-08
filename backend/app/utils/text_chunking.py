"""Split long text into overlapping chunks for RAG indexing."""

from __future__ import annotations


def split_text_into_chunks(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Split text into chunks of at most `chunk_size` characters with `overlap` between adjacent chunks.

    Uses paragraph boundaries when possible, then falls back to character windows.
    """
    text = (text or "").strip()
    if not text:
        return []

    chunk_size = max(200, chunk_size)
    overlap = max(0, min(overlap, chunk_size // 2))

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split("\n\n")
    buf = ""

    for para in paragraphs:
        p = para.strip()
        if not p:
            continue
        candidate = f"{buf}\n\n{p}".strip() if buf else p
        if len(candidate) <= chunk_size:
            buf = candidate
            continue

        if buf:
            chunks.extend(_window_chunk(buf, chunk_size, overlap))
        if len(p) <= chunk_size:
            buf = p
        else:
            chunks.extend(_window_chunk(p, chunk_size, overlap))
            buf = ""

    if buf:
        chunks.extend(_window_chunk(buf, chunk_size, overlap))

    # Deduplicate while preserving order (overlap can duplicate short tails)
    seen: set[str] = set()
    out: list[str] = []
    for c in chunks:
        c = c.strip()
        if len(c) < 10:
            continue
        key = c[:200]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)

    return out if out else [text[:chunk_size]]


def _window_chunk(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    parts: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        piece = text[start : start + chunk_size].strip()
        if piece:
            parts.append(piece)
        start += step
    return parts
