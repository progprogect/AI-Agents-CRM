# RAG: метрики, wide recall и следующий шаг (rerank / hybrid)

## Что уже есть в логах (debug)

- `rag_retrieval_ms` — время векторного поиска по агенту.
- `rag_context_chars` / `rag_context_budget` — сколько символов ушло в промпт после упаковки.
- `rag_vector_recall_k` — сколько кандидатов запрошено у поиска (`max(top_k из конфига, RAG_VECTOR_RECALL_K или `rag.retrieval.vector_recall_k`)).

Смотрите структурированные поля `extra` у сообщений из [`rag_service`](../app/services/rag_service.py).

## Wide recall (без отдельной rerank-модели)

По умолчанию retrieval запрашивает не меньше **`RAG_VECTOR_RECALL_K`** (24) чанков/документов, даже если в UI `top_k` меньше. Итоговый текст по-прежнему ограничен **`RAG_CONTEXT_MAX_CHARS`** / `rag.retrieval.max_context_chars`.

Переменные окружения:

- `RAG_VECTOR_RECALL_K` — нижняя граница числа кандидатов (4–200).
- Пер-агент: `rag.retrieval.vector_recall_k` в конфиге агента.

## Golden-set (минимальный шаблон для оценки)

В репозитории есть заготовка: [`rag_golden_set_template.csv`](rag_golden_set_template.csv) (колонки `query`, `expected_doc_id_or_title`, `notes`).

Создайте свою таблицу или расширьте шаблон:

| query | expected_doc_id_or_title | notes |
|-------|-------------------------|-------|
| пример запроса пользователя | идентификатор или заголовок чанка | опционально |

Периодически прогоняйте запросы на тестовом агенте и вручную проверяйте, попадёт ли нужный фрагмент в топ после бюджета.

## Когда добавлять rerank или hybrid

- **Rerank** (cross-encoder или API): имеет смысл, если при росте базы **precision** падает: в «широком» top-K попадают лишние чанки, а бюджет отрезает нужные. Делать после сбора метрик и golden-set.
- **Hybrid (BM25 + вектор):** если много точных совпадений (артикулы, коды, имена), которые семантика промахивает. Требует индекса полнотекстового поиска (PostgreSQL `tsvector` и т.п.).

Подробнее: [`rag_rerank_hybrid.md`](rag_rerank_hybrid.md).
