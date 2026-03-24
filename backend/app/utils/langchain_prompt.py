"""Helpers for LangChain prompt templates.

`ChatPromptTemplate` (and string-based message templates in LangChain) treat `{name}`
as input variables. Text that contains literal curly braces — JSON examples, JSON Schema
from `PydanticOutputParser.get_format_instructions()`, code snippets — must be escaped
or the template engine fails at format/invoke time (e.g. "Missing some input keys").
"""

from __future__ import annotations


def escape_braces_for_chat_template(text: str) -> str:
    """Return text safe to embed in a LangChain chat template string.

    Doubles each ``{`` and ``}`` so they render as literals after template processing.
    Do not pass strings that already contain real placeholders (e.g. ``{message}``);
    escape only the static segments, then concatenate with unescaped template parts.
    """
    return text.replace("{", "{{").replace("}", "}}")
