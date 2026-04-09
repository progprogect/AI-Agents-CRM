# LangChain stack: AS-IS, gaps и путь миграции

## Текущее состояние (AS-IS)

| Компонент | Реализация |
|-----------|------------|
| Основной чат | **`create_agent`** из `langchain.agents` (граф на LangGraph внутри пакета `langchain`) + `ainvoke` ([`agent_chain.py`](../app/chains/agent_chain.py)); `debug` включается из `settings.debug` |
| Эскалация | `ChatPromptTemplate` + `BaseChatModel`: основной путь — **`with_structured_output(EscalationDecision)`**; при сбое — текстовый ответ + разбор JSON; fallback-парсер — `PydanticOutputParser` из **`langchain_core`** ([`escalation_chain.py`](../app/chains/escalation_chain.py)) |
| RAG | `langchain_core.embeddings.Embeddings` + самописный поиск в PostgreSQL (`rag_chunks`); бюджет контекста, опционально **широкий recall** перед бюджетом. DynamoDB **не поддерживается** |
| Инструменты | Сейчас **не подключены** (`create_agent` с пустым списком tools); отдельные tools можно добавить позже |

## Разрыв с рекомендациями LangChain 1.x

- **Основной чат** переведён на **`create_agent`**; при необходимости явного checkpointing / HITL можно вынести шаги в отдельный **LangGraph** снаружи `AgentService`.
- **Эскалация:** структурированный вывод через `with_structured_output(Pydantic)`; fallback — JSON + `PydanticOutputParser` только для инструкций формата в текстовой ветке.
- **LCEL** (`RunnableSequence`): для детерминированных пайплайнов (retrieval → truncate → prompt).

## Целевой путь миграции (поэтапно)

1. **Сделано:** главный агент на `create_agent`; эскалация на `Runnable` + structured output с fallback; RAG: чанки, бюджет, wide recall; логи с `conversation_id` / `agent_id` по цепочке; шаблон golden-set: [`rag_golden_set_template.csv`](rag_golden_set_template.csv).
2. **Среднесрок:** при необходимости — **rerank** / **hybrid** (метрики и wide recall: [`rag_metrics_and_rerank.md`](rag_metrics_and_rerank.md); обзор rerank: [`rag_rerank_hybrid.md`](rag_rerank_hybrid.md)).
3. **Долгосрок (опционально):** отдельный LangGraph-оркестратор вокруг шагов, если понадобятся долгие сценарии и устойчивое состояние.

## Зависимости

- **`langchain`:** тянет `langchain-core` и **`langgraph`** (агент `create_agent` собран как compiled graph).
- **`langchain-community`:** удалена из `requirements.txt` (не использовалась).
- **`langchain-classic`:** **не используется** (раньше: `AgentExecutor` / `create_openai_tools_agent`).
