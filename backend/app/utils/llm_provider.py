"""LLM and embeddings provider abstraction for OpenAI and Google AI Studio."""

import logging
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.config import Settings, get_settings
from app.models.agent_config import AgentConfig, EmbeddingsConfig
from app.utils.model_params import requires_max_completion_tokens

logger = logging.getLogger(__name__)

# Embedding dimensions for compatibility with existing RAG documents (OpenAI text-embedding-3-small)
RAG_EMBEDDING_DIMENSIONS = 1536


def _get_google_api_key_sync(settings: Settings) -> Optional[str]:
    """Get Google AI Studio API key from settings (sync)."""
    key = settings.google_ai_studio_api_key
    if key:
        return key.strip().strip('"').strip("'")
    return None


def create_chat_model(
    agent_config: AgentConfig,
    openai_api_key: str,
    google_api_key: Optional[str] = None,
) -> BaseChatModel:
    """
    Create chat model (OpenAI or Google) based on agent config.

    Args:
        agent_config: Agent configuration with llm.provider and llm.model
        openai_api_key: OpenAI API key (required for openai provider)
        google_api_key: Google API key (required for google_ai_studio provider)

    Returns:
        BaseChatModel instance (ChatOpenAI or ChatGoogleGenerativeAI)
    """
    provider = getattr(agent_config.llm, "provider", None) or "openai"
    model = agent_config.llm.model or "gpt-4o-mini"
    temperature = agent_config.llm.temperature
    max_tokens = agent_config.llm.max_output_tokens
    timeout = agent_config.llm.timeout

    if provider == "google_ai_studio":
        if not google_api_key:
            raise RuntimeError(
                "Google AI Studio API key not found. Set GOOGLE_AI_STUDIO_API or Google_AI_Studio_API env var."
            )
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=google_api_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
            timeout=timeout,
        )

    # Default: OpenAI
    llm_kwargs: dict = {
        "model": model,
        "temperature": temperature,
        "openai_api_key": openai_api_key,
        "timeout": timeout,
    }
    if requires_max_completion_tokens(model):
        llm_kwargs["model_kwargs"] = {"max_completion_tokens": max_tokens}
    else:
        llm_kwargs["max_tokens"] = max_tokens

    return ChatOpenAI(**llm_kwargs)


def create_embeddings(
    embeddings_config: EmbeddingsConfig,
    openai_api_key: str,
    google_api_key: Optional[str] = None,
) -> Embeddings:
    """
    Create embeddings model (OpenAI or Google) based on config.

    Args:
        embeddings_config: Embeddings configuration with provider and model
        openai_api_key: OpenAI API key
        google_api_key: Google API key

    Returns:
        Embeddings instance
    """
    provider = embeddings_config.provider or "openai"
    model = embeddings_config.model or "text-embedding-3-small"

    if provider == "google_ai_studio":
        if not google_api_key:
            raise RuntimeError(
                "Google AI Studio API key not found for embeddings. Set GOOGLE_AI_STUDIO_API env var."
            )
        # Google models: text-embedding-004, gemini-embedding-001
        google_model = "text-embedding-004" if "embedding-3" in model or "ada" in model else model
        return GoogleGenerativeAIEmbeddings(
            model=google_model,
            google_api_key=google_api_key,
            output_dimensionality=RAG_EMBEDDING_DIMENSIONS,
        )

    return OpenAIEmbeddings(
        model=model,
        openai_api_key=openai_api_key,
    )


def _get_vision_provider(agent_config: AgentConfig | dict) -> str:
    """Get vision provider from agent config (rag.vision_provider or llm.provider)."""
    if isinstance(agent_config, dict):
        rag = agent_config.get("rag") or {}
        llm = agent_config.get("llm") or {}
        return rag.get("vision_provider") or llm.get("provider") or "openai"
    return (
        getattr(agent_config.rag, "vision_provider", None)
        or getattr(agent_config.llm, "provider", None)
        or "openai"
    )


def get_rag_embeddings_config(agent_config: AgentConfig | dict) -> EmbeddingsConfig:
    """
    Get embeddings config for RAG from agent config.
    Uses rag.embeddings_provider when set, else agent_config.embeddings.
    """
    if isinstance(agent_config, dict):
        agent_config = AgentConfig.from_dict(agent_config)
    settings = get_settings()
    rag_provider = getattr(agent_config.rag, "embeddings_provider", None) or "openai"
    base = agent_config.embeddings

    if rag_provider == "google_ai_studio":
        return EmbeddingsConfig(
            provider="google_ai_studio",
            model="text-embedding-004",
            dimensions=RAG_EMBEDDING_DIMENSIONS,
        )
    return EmbeddingsConfig(
        provider="openai",
        model=base.model or settings.openai_embedding_model,
        dimensions=base.dimensions or settings.openai_embedding_dimensions,
    )
