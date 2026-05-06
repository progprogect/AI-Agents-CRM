#!/usr/bin/env python3
"""Многоходовая симуляция чата по фикстуре «Дай Лапу» без OpenAI и без БД.

Использует MemorySaver для чекпоинта и умный мок LLM (переходы YES/NO, извлечение
полей, основные ответы). Запуск из каталога backend:

  .venv/bin/python scripts/simulate_vet_dialog.py

Это не замена проверки продакшен-URL, но воспроизводит тот же граф AgentChain,
что и на сервере после деплоя кода.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

# --- До импорта AgentChain: в памяти чекпоинт + сброс кэша графа ---
from langgraph.checkpoint.memory import MemorySaver

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import app.chains.agent_chain as agent_chain_module
import app.storage.postgres_checkpointer as pg_ckpt

pg_ckpt._checkpointer = MemorySaver()
agent_chain_module._graph_cache.clear()

from app.chains.agent_chain import AgentChain  # noqa: E402
from app.models.agent_config import AgentConfig  # noqa: E402


FIXTURE = _BACKEND / "tests" / "fixtures" / "day_lapu_vet_schedule_anchor_agent.json"


class SmartLLM:
    """Отвечает на вызовы графа: извлечение JSON, YES/NO переходы, основной текст."""

    def __init__(self, share_template: str) -> None:
        self._share_template = share_template
        self.main_turn = 0

    def _flatten(self, messages: list) -> str:
        parts: list[str] = []
        for m in messages:
            c = getattr(m, "content", "")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and "text" in b:
                        parts.append(str(b["text"]))
                    else:
                        parts.append(str(b))
        return "\n".join(parts)

    async def ainvoke(self, messages: list):
        blob = self._flatten(messages)

        # Collection extraction (required + collect gate)
        if "Extract the following fields" in blob and "Return ONLY a JSON object" in blob:
            return AIMessage(content=json.dumps({}, ensure_ascii=False))

        # Переходы (pre и post): смотрим блок последних реплик
        if "Evaluate whether the following condition is satisfied" in blob:
            tail = blob.split("Recent conversation:", 1)[-1] if "Recent conversation:" in blob else blob
            closure = (
                "все понятно" in tail.lower()
                or "всё понятно" in tail.lower()
                or "Все понятно" in tail
            )
            return AIMessage(content="YES" if closure else "NO")

        # Шаг «Рекомендация»: системный промпт просит дословный текст из шаблона
        if "Ответь пользователю ТОЛЬКО следующим текстом" in blob or (
            self._share_template and self._share_template[:40] in blob
        ):
            return AIMessage(content=self._share_template)

        # Обычный диалог (имитация Татьяны)
        self.main_turn += 1
        if self.main_turn == 1:
            return AIMessage(
                content="Привет 🐾 Я Татьяна. Расскажи, что беспокоит Мухтара?"
            )
        if self.main_turn == 2:
            return AIMessage(
                content="Поняла. Уточни: чешется давно? Есть подсыхи на коже?"
            )
        return AIMessage(
            content="Спасибо за детали. Опишу наблюдения и дам общие шаги; при ухудшении — к ветеринару.\n\n1) Оградите от расчёсывания...\n[это не диагноз]"
        )


async def main() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cfg = AgentConfig.from_dict(raw)

    tpls = cfg.prompts.templates or {}
    share_msg = str(tpls.get("recommendation_share_message") or "").strip()
    llm = SmartLLM(share_template=share_msg)
    class LF:
        async def get_chat_model(self, agent_config):
            return llm

    factory = LF()

    chain = AgentChain(cfg, llm_factory=factory)
    cid = "sim-conv-1"

    turns = [
        "Привет!",
        "У меня собака Мухтар, чешется ухо пару дней",
        "Чешется второй день, есть корочки",
        "Все понятно",
    ]

    print("=== Симуляция диалога (та же цепочка, что на сервере) ===\n")

    for i, user_text in enumerate(turns, 1):
        print(f"—— Пользователь [{i}]: {user_text}")
        out = await chain.generate_response(
            user_text,
            conversation_id=cid,
            moderation_service=None,
            escalation_service=None,
            rag_service=None,
            is_reply_stale=None,
            seed_messages=[] if i > 1 else [],
        )
        resp = out.get("response") or ""
        qr = out.get("quick_replies") or []
        preview = (resp[:420] + "…") if len(resp) > 420 else resp
        print(f"—— Бот       [{i}]: {preview}")
        print(f"    quick_replies: {qr}")
        print()

    print("=== Проверка последнего шага ===")
    last = out.get("response") or ""
    share_tpl = (cfg.prompts.templates or {}).get("recommendation_share_message", "")
    if share_tpl and share_tpl.strip() in last.replace("\r\n", "\n"):
        print("OK: текст ответа содержит recommendation_share_message из конфига.")
    else:
        print("ВНИМАНИЕ: финальный ответ не совпал с шаблоном (мок / температура).")


if __name__ == "__main__":
    asyncio.run(main())
