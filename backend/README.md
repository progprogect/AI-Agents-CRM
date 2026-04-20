# AI Agents CRM — Backend

Backend API for the AI Agents CRM system.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Run the application:
```bash
python -m app.main
```

Or with uvicorn:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

### Health Check
- `GET /health` - Health check endpoint

### Chat API
- `POST /api/v1/chat/conversations` - Create conversation
- `GET /api/v1/chat/conversations/{id}` - Get conversation
- `POST /api/v1/chat/conversations/{id}/messages` - Send message
- `GET /api/v1/chat/conversations/{id}/messages` - Get messages

### Agents API
- `POST /api/v1/agents/` - Create agent
- `GET /api/v1/agents/{id}` - Get agent
- `GET /api/v1/agents/` - List agents
- `PUT /api/v1/agents/{id}` - Update agent
- `DELETE /api/v1/agents/{id}` - Delete agent

### Admin API
- `GET /api/v1/admin/conversations` - List conversations
- `POST /api/v1/admin/conversations/{id}/handoff` - Handoff to human
- `POST /api/v1/admin/conversations/{id}/return` - Return to AI
- `GET /api/v1/admin/audit` - Get audit logs
- `GET /api/v1/admin/stats` - Get statistics

### WebSocket
- `WS /ws/{conversation_id}` - Real-time chat WebSocket

## Development

The application uses:
- FastAPI for API framework
- Pydantic for data validation
- PostgreSQL for data storage
- OpenSearch for vector search
- Redis for caching
- OpenAI API for LLM and embeddings







# CI/CD Test

