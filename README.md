# AI Agents CRM

AI-powered assistant platform for customer conversations and CRM workflows. Built with FastAPI (backend) and Next.js (frontend), using OpenAI API for LLM capabilities.

## Features

- **Web Chat Interface**: Real-time chat between patients and AI agent
- **Admin Panel**: Monitor conversations, manage agents, perform handoffs
- **LLM-based Escalation**: Intelligent detection of when human intervention is needed
- **RAG Support**: Retrieval-Augmented Generation for context-aware responses
- **Privacy-First**: Temporary message storage (48h TTL), no PII for training
- **Real-time Updates**: WebSocket-based real-time communication
- **Agent Configuration**: YAML-based agent configuration without code changes

## Architecture

### Backend
- **FastAPI**: REST API and WebSocket server
- **OpenAI API**: LLM generation (`gpt-4o-mini`), embeddings (`text-embedding-3-small`), moderation
- **Storage (PostgreSQL + Redis):**
  - PostgreSQL: primary storage for conversations, messages, agents, RAG chunks, audit logs
  - Redis: debounce queue, timer triggers, cache
- **LangChain** (`create_agent`, LangGraph via `langchain` package): LLM orchestration and tools; см. `backend/docs/architecture_langchain.md`

> **Note:** DynamoDB and AWS-native services are **not supported**. The project runs exclusively on PostgreSQL + Redis (e.g. Railway, Render, or any Postgres/Redis provider).

### Frontend
- **Next.js 14**: React framework with App Router
- **TypeScript**: Type-safe development
- **TailwindCSS**: Styling
- **WebSocket Client**: Real-time communication

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (Railway, Supabase, or self-hosted)
- Redis (Railway, Upstash, or self-hosted)
- OpenAI API Key

## Installation

### Backend

1. Navigate to backend directory:
```bash
cd backend
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file:
```bash
cp .env.example .env
```

5. Configure environment variables in `.env`:
```env
# Application
APP_NAME=Doctor Agent API
APP_VERSION=0.1.0
ENVIRONMENT=development
DEBUG=true

# OpenAI
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# DynamoDB
DYNAMODB_TABLE_CONVERSATIONS=doctor-agent-conversations
DYNAMODB_TABLE_MESSAGES=doctor-agent-messages
DYNAMODB_TABLE_AGENTS=doctor-agent-agents
DYNAMODB_TABLE_AUDIT_LOGS=doctor-agent-audit-logs
DYNAMODB_ENDPOINT_URL=http://localhost:8000  # For local DynamoDB

# OpenSearch
OPENSEARCH_ENDPOINT=http://localhost:9200
OPENSEARCH_USE_SSL=false
OPENSEARCH_VERIFY_CERTS=false

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Security
ADMIN_TOKEN=your_admin_token_here
RATE_LIMIT_PER_MINUTE=60

# CORS
CORS_ORIGINS=["http://localhost:3000"]
```

6. Run the application:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create `.env.local` file:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

4. Run development server:
```bash
npm run dev
```

5. Open [http://localhost:3000](http://localhost:3000) in your browser

## Usage

### Creating an Agent

1. Create a YAML configuration file in `configs/agent_configs/`:
```yaml
agent_id: "doctor_001"
version: "1.0.0"
role: "doctor_assistant"
project: "doctor_agent_mvp"
environment: "production"
# ... (see configs/agent_configs/doctor_001.yaml for full example)
```

2. Use the Admin Panel or API to create the agent:
```bash
curl -X POST http://localhost:8000/api/v1/agents/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_admin_token" \
  -d '{
    "agent_id": "doctor_001",
    "config": { ... }
  }'
```

### Starting a Chat

1. Navigate to `/chat/doctor_001` (or your agent ID)
2. The system will create a new conversation automatically
3. Start chatting with the AI agent

### Admin Panel

1. Navigate to `/admin`
2. View conversations, manage agents, perform handoffs
3. Monitor audit logs and statistics

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
doctor-agent/
├── backend/
│   ├── app/
│   │   ├── api/           # API endpoints and WebSocket handlers
│   │   ├── services/      # Business logic services
│   │   ├── models/        # Pydantic models
│   │   ├── storage/       # Database clients (DynamoDB, OpenSearch, Redis)
│   │   ├── chains/       # LangChain chains
│   │   ├── tools/        # LangChain tools
│   │   ├── utils/        # Utility functions
│   │   └── main.py       # FastAPI application
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/              # Next.js App Router pages
│   ├── components/       # React components
│   ├── lib/             # Utilities and hooks
│   └── package.json
├── configs/
│   └── agent_configs/   # Agent YAML configurations
└── README.md
```

## Configuration

### Agent Configuration

Agents are configured via YAML files. See `configs/agent_configs/doctor_001.yaml` for a complete example.

Key configuration sections:
- **Privacy**: Message retention, metadata handling
- **Security**: Access control, audit logging
- **LLM**: OpenAI model selection and parameters
- **Moderation**: Content moderation settings
- **Escalation**: LLM-based escalation detection
- **RAG**: Document retrieval configuration

## Security

- **Authentication**: Bearer token authentication for admin endpoints
- **Rate Limiting**: Configurable rate limiting per IP
- **Input Validation**: Pydantic schemas for all inputs
- **Error Handling**: Centralized error handling with request IDs

## Monitoring

- **Structured Logging**: JSON-formatted logs in production
- **Request IDs**: Every request has a unique ID for tracing
- **Metrics**: Basic metrics collection (can be extended)

## Development

### Running Tests

```bash
cd backend
pytest
```

### Code Quality

```bash
# Backend
cd backend
black app/
isort app/
mypy app/

# Frontend
cd frontend
npm run lint
```

## Deployment

### Backend (AWS ECS Fargate)

1. Build Docker image:
```bash
cd backend
docker build -t doctor-agent-backend .
```

2. Push to ECR:
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker tag doctor-agent-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/doctor-agent-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/doctor-agent-backend:latest
```

3. Deploy to ECS Fargate (configure via Terraform/CDK)

### Frontend (Vercel/Netlify)

1. Connect repository to Vercel/Netlify
2. Configure environment variables
3. Deploy

## License

[Your License Here]

## Support

For issues and questions, please open an issue on GitHub.








