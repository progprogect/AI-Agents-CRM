"""Provider-specific moderation implementations (OpenAI Moderations API vs Gemini JSON classifier)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.config import Settings, get_settings
from app.models.agent_config import AgentConfig
from app.models.moderation import ModerationCategory, ModerationResult
from app.services.llm_factory import LLMFactory
from app.utils.llm_provider import _get_google_api_key_sync

logger = logging.getLogger(__name__)

# Map OpenAI moderation category keys (incl. omni-moderation) to coarse enum
_OPENAI_KEY_TO_COARSE: dict[str, ModerationCategory] = {
    "hate": ModerationCategory.HATE,
    "hate/threatening": ModerationCategory.HATE,
    "harassment": ModerationCategory.HARASSMENT,
    "harassment/threatening": ModerationCategory.HARASSMENT,
    "self-harm": ModerationCategory.SELF_HARM,
    "self-harm/intent": ModerationCategory.SELF_HARM,
    "self-harm/instructions": ModerationCategory.SELF_HARM,
    "sexual": ModerationCategory.SEXUAL,
    "sexual/minors": ModerationCategory.SEXUAL,
    "violence": ModerationCategory.VIOLENCE,
    "violence/graphic": ModerationCategory.VIOLENCE,
    "illicit": ModerationCategory.VIOLENCE,
    "illicit/violent": ModerationCategory.VIOLENCE,
}


def _openai_response_to_result(result: Any) -> ModerationResult:
    """Map OpenAI moderations API result row to ModerationResult."""
    row = result.results[0]
    cat_dump = row.categories.model_dump()
    score_obj = row.category_scores
    scores_dump = score_obj.model_dump() if hasattr(score_obj, "model_dump") else {}

    categories: dict[str, bool] = {}
    category_scores: dict[str, float] = {}
    primary_category = ModerationCategory.NONE
    max_score = -1.0

    for category, flagged in cat_dump.items():
        score = float(getattr(score_obj, category, scores_dump.get(category, 0.0)))
        categories[category] = bool(flagged)
        category_scores[category] = score
        coarse = _OPENAI_KEY_TO_COARSE.get(category)
        if coarse is None:
            continue
        if bool(flagged) and score > max_score:
            max_score = score
            primary_category = coarse

    return ModerationResult(
        flagged=row.flagged,
        categories=categories,
        category_scores=category_scores,
        category=primary_category,
    )


async def moderate_openai(
    content: str,
    agent_config: AgentConfig,
    llm_factory: LLMFactory,
) -> ModerationResult:
    """Moderate via OpenAI Moderations API."""
    client = await llm_factory.get_client(agent_config.agent_id)
    mod = agent_config.moderation
    model = mod.model or "omni-moderation-latest"
    response = await client.moderate(content, model=model)
    return _openai_response_to_result(response)


_GEMINI_MODERATION_SYSTEM = """You are a content safety classifier. Analyze the user text for policy violations.
Respond with ONLY valid JSON, no markdown, no other text. Schema:
{
  "flagged": boolean,
  "category_scores": {
    "hate": number 0-1,
    "harassment": number 0-1,
    "sexual": number 0-1,
    "self-harm": number 0-1,
    "violence": number 0-1
  }
}
Use 0.0-1.0 confidence. Set flagged true if any category is clearly problematic (typically score >= 0.5 for that category)."""


def _parse_json_from_llm(text: str) -> dict[str, Any]:
    """Extract JSON object from model output (strip fences)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def _gemini_json_to_result(data: dict[str, Any]) -> ModerationResult:
    flagged = bool(data.get("flagged", False))
    raw_scores = data.get("category_scores") or {}
    keys = ["hate", "harassment", "sexual", "self-harm", "violence"]
    category_scores: dict[str, float] = {}
    categories: dict[str, bool] = {}
    primary = ModerationCategory.NONE
    max_s = -1.0
    mapping = {
        "hate": ModerationCategory.HATE,
        "harassment": ModerationCategory.HARASSMENT,
        "sexual": ModerationCategory.SEXUAL,
        "self-harm": ModerationCategory.SELF_HARM,
        "violence": ModerationCategory.VIOLENCE,
    }
    for k in keys:
        v = float(raw_scores.get(k, 0.0))
        category_scores[k] = v
        categories[k] = v >= 0.5
        coarse = mapping.get(k)
        if coarse is not None and v > max_s:
            max_s = v
            primary = coarse
    return ModerationResult(
        flagged=flagged,
        categories=categories,
        category_scores=category_scores,
        category=primary if flagged else ModerationCategory.NONE,
    )


async def moderate_gemini(
    content: str,
    agent_config: AgentConfig,
    settings: Optional[Settings] = None,
) -> ModerationResult:
    """Classify content with Gemini (JSON). Not identical to OpenAI Moderation API."""
    settings = settings or get_settings()
    api_key = _get_google_api_key_sync(settings)
    if not api_key:
        raise RuntimeError(
            "Google AI Studio API key not found. Set GOOGLE_AI_STUDIO_API env var."
        )
    model_name = agent_config.moderation.model or "gemini-2.0-flash"

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0.0,
        max_output_tokens=512,
    )
    messages = [
        SystemMessage(content=_GEMINI_MODERATION_SYSTEM),
        HumanMessage(content=f"Text to classify:\n\n{content}"),
    ]
    resp = await llm.ainvoke(messages)
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        data = _parse_json_from_llm(raw)
        return _gemini_json_to_result(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning(
            "Gemini moderation JSON parse failed: %s; raw=%s",
            e,
            raw[:500],
        )
        return ModerationResult(
            flagged=False,
            categories={},
            category_scores={},
            category=ModerationCategory.NONE,
        )


async def moderate_for_agent(
    content: str,
    agent_config: AgentConfig,
    llm_factory: LLMFactory,
) -> ModerationResult:
    """Dispatch to OpenAI or Gemini moderation backend."""
    provider = agent_config.moderation.provider or "openai"
    if provider == "google_ai_studio":
        return await moderate_gemini(content, agent_config, llm_factory.settings)
    return await moderate_openai(content, agent_config, llm_factory)
