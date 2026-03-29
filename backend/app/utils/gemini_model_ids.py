"""Gemini / vision model id constants and resolver for image understanding.

Used for RAG image indexing and inbound user images in chat (single source of truth).
See https://ai.google.dev/gemini-api/docs/models for official model codes.
"""

from typing import Any

# OpenAI multimodal vision model (chat completions API)
OPENAI_VISION_MODEL_ID = "gpt-4o"

# When rag.vision_model is unset (Google AI Studio vision path)
GEMINI_VISION_DEFAULT = "gemini-3.1-pro-preview"


def _get_rag_vision_model_field(agent_config: Any) -> str | None:
    """Read optional rag.vision_model from dict or AgentConfig."""
    if agent_config is None:
        return None
    if isinstance(agent_config, dict):
        rag = agent_config.get("rag")
        if rag is None:
            return None
        if isinstance(rag, dict):
            v = rag.get("vision_model")
        else:
            v = getattr(rag, "vision_model", None)
    else:
        rag = getattr(agent_config, "rag", None)
        if rag is None:
            return None
        v = getattr(rag, "vision_model", None)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def resolve_vision_model_id(agent_config: Any) -> str:
    """Return API model id for image description (RAG + inbound chat images).

    - openai / other non-Google vision provider: ``gpt-4o``.
    - google_ai_studio: ``rag.vision_model`` if set, else ``gemini-3.1-pro-preview``.
    """
    from app.utils.llm_provider import _get_vision_provider

    provider = _get_vision_provider(agent_config) if agent_config is not None else "openai"
    if provider != "google_ai_studio":
        return OPENAI_VISION_MODEL_ID
    explicit = _get_rag_vision_model_field(agent_config)
    if explicit:
        return explicit
    return GEMINI_VISION_DEFAULT
