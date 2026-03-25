"""Custom validators for agent configuration."""

import re
from typing import Any

from pydantic import field_validator, model_validator


def validate_agent_id(agent_id: str) -> str:
    """Validate agent ID format."""
    if not agent_id or not agent_id.strip():
        raise ValueError("Agent ID cannot be empty")
    if len(agent_id) > 100:
        raise ValueError("Agent ID cannot exceed 100 characters")
    # Allow alphanumeric, underscore, hyphen
    if not re.match(r"^[a-zA-Z0-9_-]+$", agent_id):
        raise ValueError(
            "Agent ID can only contain alphanumeric characters, underscores, and hyphens"
        )
    return agent_id.strip()


def validate_temperature(temperature: float) -> float:
    """Validate temperature value."""
    if not 0.0 <= temperature <= 2.0:
        raise ValueError("Temperature must be between 0.0 and 2.0")
    return temperature


def validate_max_tokens(max_tokens: int) -> int:
    """Validate max_tokens value."""
    if max_tokens < 1:
        raise ValueError("max_tokens must be at least 1")
    if max_tokens > 4096:
        raise ValueError("max_tokens cannot exceed 4096")
    return max_tokens


def validate_empathy_level(level: int) -> int:
    """Validate empathy level."""
    if not 0 <= level <= 10:
        raise ValueError("Empathy level must be between 0 and 10")
    return level


def validate_depth_level(level: int) -> int:
    """Validate depth level."""
    if not 0 <= level <= 10:
        raise ValueError("Depth level must be between 0 and 10")
    return level


def validate_llm_provider(provider: str) -> str:
    """Validate LLM provider."""
    valid_providers = ["openai", "aws_bedrock"]
    if provider not in valid_providers:
        raise ValueError(f"LLM provider must be one of: {', '.join(valid_providers)}")
    return provider


def validate_embeddings_provider(provider: str) -> str:
    """Validate embeddings provider."""
    valid_providers = ["openai", "aws_bedrock"]
    if provider not in valid_providers:
        raise ValueError(
            f"Embeddings provider must be one of: {', '.join(valid_providers)}"
        )
    return provider


def validate_moderation_provider(provider: str) -> str:
    """Validate moderation provider."""
    valid_providers = ["openai", "google_ai_studio"]
    if provider not in valid_providers:
        raise ValueError(
            f"Moderation provider must be one of: {', '.join(valid_providers)}"
        )
    return provider


def validate_moderation_mode(mode: str) -> str:
    """Validate moderation mode."""
    valid_modes = ["pre", "post", "pre_and_post"]
    if mode not in valid_modes:
        raise ValueError(f"Moderation mode must be one of: {', '.join(valid_modes)}")
    return mode


def validate_openai_model(model: str) -> str:
    """Validate OpenAI model name."""
    valid_models = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ]
    if model not in valid_models:
        # Allow other models but log warning
        return model
    return model


def validate_embedding_model(model: str) -> str:
    """Validate embedding model name."""
    valid_models = [
        "text-embedding-3-large",
        "text-embedding-3-small",
        "text-embedding-ada-002",
    ]
    if model not in valid_models:
        # Allow other models but log warning
        return model
    return model


def validate_rag_top_k(top_k: int) -> int:
    """Validate RAG top_k parameter."""
    if top_k < 1:
        raise ValueError("RAG top_k must be at least 1")
    if top_k > 50:
        raise ValueError("RAG top_k cannot exceed 50")
    return top_k


def validate_rag_score_threshold(threshold: float) -> float:
    """Validate RAG score threshold."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("RAG score threshold must be between 0.0 and 1.0")
    return threshold








