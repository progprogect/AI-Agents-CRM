"""LLM (with static fallback) text for Telegram user reminders."""

from __future__ import annotations

import logging
from typing import Any

from app.models.agent_config import AgentConfig
from app.services.llm_factory import get_llm_factory
from langchain_core.messages import HumanMessage as _HM, SystemMessage as _SM

logger = logging.getLogger(__name__)

CATEGORY_LABEL_RU: dict[str, str] = {
    "vaccination": "прививка",
    "treatment": "обработка от паразитов",
    "food_order": "заказ корма",
    "other": "напоминание",
}


def _fallback_text(category: str, user_note: str) -> str:
    label = CATEGORY_LABEL_RU.get(category, "напоминание")
    base = f"Напоминание: {label}."
    if user_note.strip():
        return f"{base}\n\n{user_note.strip()}"
    return f"{base} Не забудьте, если планировали — уточните детали у врача или в клинике."


def _format_questionnaire_block(q: dict[str, str]) -> str:
    if not q:
        return "(анкета не заполнена)"
    lines = [f"- {k}: {v}" for k, v in list(q.items())[:20]]
    return "\n".join(lines)


async def generate_reminder_message(
    agent_config: AgentConfig,
    *,
    category: str,
    user_note: str,
    questionnaire_values: dict[str, str],
) -> str:
    """1–3 short friendly sentences; no medical advice beyond general reminder."""
    label = CATEGORY_LABEL_RU.get(category, "напоминание")
    try:
        llm = await get_llm_factory().get_chat_model(agent_config)
        system = (
            "You write short reminder messages in Russian for a veterinary chat assistant. "
            "1–3 sentences, warm and clear. No diagnosis or drug advice. "
            "If the user left a custom note, reflect it. Use questionnaire facts only as context (pet name, etc.). "
            "Do not invent medical facts not in the data."
        )
        user = (
            f"Тип напоминания: {label}.\n"
            f"Заметка пользователя: {user_note.strip() or '(нет)'}\n\n"
            f"Данные из анкеты:\n{_format_questionnaire_block(questionnaire_values)}"
        )
        result = await llm.ainvoke([_SM(content=system), _HM(content=user)])
        text = result.content if hasattr(result, "content") else str(result)
        if isinstance(text, list):
            text = " ".join(
                c.get("text", "") if isinstance(c, dict) else str(c) for c in text
            )
        text = str(text).strip()
        if len(text) < 10:
            return _fallback_text(category, user_note)
        return text[:1200]
    except Exception as exc:
        logger.warning("reminder LLM generation failed: %s", exc)
        return _fallback_text(category, user_note)
