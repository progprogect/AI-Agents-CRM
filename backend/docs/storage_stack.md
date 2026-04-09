# Storage Stack

## Supported backends

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Primary storage | **PostgreSQL** | Conversations, messages, agents, RAG chunks, audit logs, secrets, channel bindings, CRM stages |
| Cache / queues | **Redis** | Agent-reply debounce, timer triggers |
| LangGraph state | **PostgreSQL** (via `langgraph-checkpoint-postgres`) | Workflow step state, conversation history in checkpoint |

## NOT supported

**DynamoDB and all AWS-native services are not supported.**

The codebase contains legacy files (`storage/dynamodb.py`, `storage/dynamodb_cache.py`, `storage/dynamodb_rag.py`) that were kept as historical reference but are never instantiated in production.  
Do **not** set `DATABASE_BACKEND=dynamodb` — that configuration key has been removed.

## Deployment requirements

- PostgreSQL ≥ 14 (Railway, Supabase, Render, self-hosted)
- Redis ≥ 6 (Railway, Upstash, self-hosted) — required only when `AGENT_REPLY_DEBOUNCE_SECONDS > 0`

## Migration from DynamoDB (historical note)

The project originally supported both backends with a `database_backend` switch.  
This switch was removed when the project standardised on PostgreSQL.  
If you are migrating existing data from DynamoDB, export it manually and import via the PostgreSQL migration scripts in `backend/migrations/`.
