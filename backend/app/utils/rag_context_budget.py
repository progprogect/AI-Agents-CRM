"""Limit total size of retrieved RAG text before injection into the LLM."""

from __future__ import annotations


def format_rag_context_with_budget(
    results: list[dict],
    max_chars: int,
) -> tuple[str, int]:
    """Build the same numbered context string as RAGService, stopping at max_chars.

    Returns (context_string, total_chars).
    """
    if not results or max_chars <= 0:
        return "", 0

    sorted_rows = sorted(
        results,
        key=lambda r: float(r.get("score", 0.0)),
        reverse=True,
    )
    parts: list[str] = []
    used = 0

    for i, result in enumerate(sorted_rows, 1):
        title = result.get("title", "Document")
        content = result.get("content", "")
        part = f"[{i}] {title}\n{content}"
        if result.get("file_url"):
            part += f"\nImage: {result['file_url']}"
        sep = "\n\n" if parts else ""
        need = len(sep) + len(part)
        if used + need <= max_chars:
            parts.append(part)
            used += need
            continue
        # Truncate this chunk to fit remainder (including truncation marker)
        room = max_chars - used - len(sep)
        suffix = "\n...[truncated]"
        if room < len(suffix) + 20:
            break
        body_room = room - len(suffix)
        truncated = part[:body_room].rstrip() + suffix
        parts.append(truncated)
        used += len(sep) + len(truncated)
        break

    return "\n\n".join(parts), min(used, max_chars)
