"""Text formatting utilities for cleaning agent responses."""

import re
from typing import Optional


def remove_markdown(text: str) -> str:
    """
    Remove markdown formatting from text.
    
    Removes common markdown syntax:
    - Bold: **text** -> text
    - Italic: *text* -> text
    - Links: [text](url) -> text
    - Code: `code` -> code
    - Code blocks: ```code``` -> code
    - Headers: # Header -> Header
    
    Args:
        text: Input text with markdown formatting
        
    Returns:
        Cleaned text without markdown syntax
        
    Examples:
        >>> remove_markdown("**Bold** text")
        'Bold text'
        >>> remove_markdown("[Link](https://example.com)")
        'Link'
    """
    if not text or not isinstance(text, str):
        return text
    
    # Remove code blocks (```code```) - must be before inline code
    text = re.sub(r'```[\s\S]*?```', '', text)
    
    # Remove inline code (`code`) - but preserve the content
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    
    # Remove links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove headers (# Header, ## Header, etc.)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    
    # Remove bold **text** -> text (non-greedy to handle multiple instances)
    text = re.sub(r'\*\*([^*]+?)\*\*', r'\1', text)
    
    # Remove italic *text* -> text (but not if it's part of **text**)
    # First handle bold, then italic separately
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'\1', text)
    
    # Remove strikethrough ~~text~~ -> text
    text = re.sub(r'~~([^~]+?)~~', r'\1', text)
    
    # Clean up extra whitespace (multiple spaces -> single space)
    text = re.sub(r' +', ' ', text)
    
    # Clean up multiple newlines (more than 2 -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def clean_agent_response(text: Optional[str]) -> Optional[str]:
    """
    Clean agent response text for plain text channels (e.g., Instagram).
    
    This is a convenience wrapper around remove_markdown that handles None values.
    
    Args:
        text: Agent response text (may be None)
        
    Returns:
        Cleaned text or None if input was None
    """
    if text is None:
        return None
    
    return remove_markdown(text)


def format_agent_text_for_whatsapp(text: str) -> str:
    """Normalize agent text for WhatsApp: bare image URLs, then strip markdown.

    The LLM is prompted to use ``[Image: URL]`` and ``![alt](URL)``. Plain
    ``remove_markdown`` would drop URLs from markdown links; here we first
    expand image patterns to raw ``https://`` URLs so they stay tappable in WhatsApp.

    Use stable, direct HTTPS URLs (e.g. public CDN); expiring signed URLs may stop
    working after a short time in the client.
    """
    if not text or not isinstance(text, str):
        return text if isinstance(text, str) else ""

    # Markdown images: ![alt](url) -> url (must run before remove_markdown)
    text = re.sub(
        r"!\[[^\]]*\]\((https?://[^)\s]+)\)",
        r"\1",
        text,
    )

    # Agent/RAG style: [Image: https://...] (case-insensitive)
    text = re.sub(
        r"(?i)\[Image:\s*(https?://[^\]]+)\]",
        r"\1",
        text,
    )

    return remove_markdown(text)

