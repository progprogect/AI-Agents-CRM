"""Utilities for determining correct model parameters."""

# Models that require max_completion_tokens instead of max_tokens
MODELS_REQUIRING_MAX_COMPLETION_TOKENS = {
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o3-mini-2025-01-31",
    "gpt-4o-2024-11-06",
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-05-13",
}


def requires_max_completion_tokens(model: str) -> bool:
    """
    Check if model requires max_completion_tokens instead of max_tokens.
    
    Args:
        model: Model name (e.g., "o1-mini", "gpt-4o")
        
    Returns:
        True if model requires max_completion_tokens, False otherwise
    """
    model_lower = model.lower()
    
    # Check exact match
    if model_lower in MODELS_REQUIRING_MAX_COMPLETION_TOKENS:
        return True
    
    # Check if model starts with any of the prefixes
    for prefix in MODELS_REQUIRING_MAX_COMPLETION_TOKENS:
        if model_lower.startswith(prefix):
            return True
    
    # Check for o1/o3/o4 variants (e.g., "o1-*", "o3-*", "o4-*")
    if model_lower.startswith("o1-") or model_lower.startswith("o3-"):
        return True
    if model_lower.startswith("o4-") or model_lower in ("o4", "o4-mini"):
        return True

    # Check for gpt-5.* models (these require max_completion_tokens)
    if model_lower.startswith("gpt-5"):
        return True
    
    # Check for specific gpt-4o versions that require max_completion_tokens
    if model_lower.startswith("gpt-4o-2024"):
        return True
    
    return False


def get_max_tokens_param(model: str) -> str:
    """
    Get the correct parameter name for max tokens based on model.
    
    Args:
        model: Model name
        
    Returns:
        "max_completion_tokens" or "max_tokens"
    """
    if requires_max_completion_tokens(model):
        return "max_completion_tokens"
    return "max_tokens"

