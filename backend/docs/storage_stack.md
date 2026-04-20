# Storage Stack

## Supported backends

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Primary storage | **PostgreSQL** | Conversations, messages, agents, RAG chunks, audit logs, secrets, channel bindings, CRM stages |
| Cache / queues | **Redis** | Agent-reply debounce, timer triggers |
| LangGraph state | **PostgreSQL** (via `langgraph-checkpoint-postgres`) | Workflow step state, conversation history in checkpoint |

## Deployment requirements

- PostgreSQL ≥ 14 (Railway, Supabase, Render, self-hosted)
- Redis ≥ 6 (Railway, Upstash, self-hosted) — required only when `AGENT_REPLY_DEBOUNCE_SECONDS > 0`
