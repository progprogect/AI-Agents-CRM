# Развёртывание AI Agents CRM на Railway

Документ описывает адаптацию проекта для развёртывания на [Railway](https://railway.app) **без AWS** — все сервисы на Railway.

---

## 1. Целевая архитектура (100% Railway)

### Стек на Railway

| Компонент | Railway-сервис | Назначение |
|-----------|----------------|------------|
| **База данных** | PostgreSQL (с pgvector) | Все данные: диалоги, сообщения, агенты, аудит, RAG-документы |
| **Кэш** | Redis (опционально) | Сессии, кэш. Можно обойтись без него на старте. |
| **Backend** | FastAPI (Docker) | API, WebSocket, бизнес-логика |
| **Frontend** | Next.js (Docker) | UI чата и админки |
| **Секреты** | Railway Variables | OpenAI API key, ADMIN_TOKEN и др. |

### Что убираем

- **AWS DynamoDB** → PostgreSQL
- **AWS Secrets Manager** → Railway Variables
- **AWS credentials** → не нужны

---

## 2. Текущее состояние и миграция

Проект сейчас использует **DynamoDB**. Для работы полностью на Railway нужна миграция на PostgreSQL.

### Объём работ

| Слой | Текущее | Целевое | Оценка |
|------|---------|---------|--------|
| Хранилище | `storage/dynamodb.py` | PostgreSQL (SQLAlchemy/asyncpg) | Средняя |
| Кэш | `storage/dynamodb_cache.py` | Redis или in-memory | Низкая |
| RAG | `storage/dynamodb_rag.py` | PostgreSQL + pgvector | Средняя |
| Secrets | AWS Secrets Manager | Env-переменные | Уже поддерживается |
| Конфиг | `config.py` | Добавить `DATABASE_URL`, убрать AWS | Низкая |

### Порядок миграции

1. Добавить PostgreSQL-клиент и модели (SQLAlchemy + asyncpg).
2. Создать миграции (Alembic) для всех таблиц.
3. Реализовать PostgreSQL-адаптеры вместо DynamoDB.
4. RAG: перейти на pgvector.
5. Кэш: Redis (Railway addon) или простой in-memory для MVP.
6. Удалить зависимости на boto3, AWS.

---

## 3. Сервисы Railway

### 3.1 PostgreSQL + pgvector

- Добавить через Railway: **New → Database → PostgreSQL** или шаблон **Postgres with pgvector**.
- Railway создаёт `DATABASE_URL` и подставляет его в переменные связанного сервиса.
- pgvector — для векторного поиска RAG.

### 3.2 Redis (опционально)

- **New → Database → Redis**.
- Появляется `REDIS_URL`.
- Можно отложить и использовать in-memory кэш.

### 3.3 Backend и Frontend

- Два сервиса из репозитория с Dockerfile.
- Root Directory: `backend` и `frontend`.

---

## 4. Переменные окружения для Railway

### 4.1 Backend (обязательные)

| Переменная | Описание | Откуда |
|------------|----------|--------|
| `OPENAI_API_KEY` | Ключ OpenAI API | Задать вручную |
| `ADMIN_TOKEN` | Токен для админ-API | Сгенерировать (`openssl rand -hex 32`) |
| `DATABASE_URL` | PostgreSQL connection string | Автоматически от Railway PostgreSQL |

### 4.2 Backend (опциональные)

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `ENVIRONMENT` | Окружение | `production` |
| `DEBUG` | Режим отладки | `false` |
| `CORS_ORIGINS` | CORS (JSON или через запятую) | `["https://your-app.railway.app"]` |
| `RATE_LIMIT_PER_MINUTE` | Лимит запросов в минуту | `60` |
| `OPENAI_MODEL` | Модель OpenAI | `gpt-4o-mini` |
| `MESSAGE_TTL_HOURS` | TTL сообщений (часы) | `48` |

### 4.3 Backend (Redis — при использовании)

| Переменная | Описание |
|------------|----------|
| `REDIS_URL` | Connection string Redis | Автоматически от Railway Redis |

### 4.4 Backend (каналы — при использовании)

| Переменная | Описание |
|------------|----------|
| `INSTAGRAM_WEBHOOK_VERIFY_TOKEN` | Токен верификации webhook Instagram |
| `INSTAGRAM_APP_SECRET` | App Secret для проверки подписи webhook |

### 4.5 Frontend (при отдельном деплое)

| Переменная | Описание |
|------------|----------|
| `NEXT_PUBLIC_API_URL` | URL backend API |
| `NEXT_PUBLIC_WS_URL` | URL WebSocket backend |

### 4.6 Railway-специфичные

| Переменная | Описание |
|------------|----------|
| `PORT` | Задаётся Railway автоматически |

---

## 5. Минимальный набор для стабильной работы

### Backend (после миграции на PostgreSQL)

```
OPENAI_API_KEY=sk-...
ADMIN_TOKEN=<сгенерировать>
DATABASE_URL=<автоматически от Railway PostgreSQL>
DATABASE_BACKEND=postgres
SECRET_ENCRYPTION_KEY=<сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
ENVIRONMENT=production
DEBUG=false
CORS_ORIGINS=["https://your-app.railway.app"]
```

### Frontend (при едином сервисе не нужны)

При деплое backend и frontend в одном сервисе переменные `NEXT_PUBLIC_API_URL` и `NEXT_PUBLIC_WS_URL` не требуются — используется тот же домен.

---

## 6. Шаги развёртывания

1. Создать проект в Railway.
2. Добавить PostgreSQL (с pgvector):
   - New → Database → **Postgres with pgvector** (или PostgreSQL + включить pgvector).
3. Добавить Redis (опционально):
   - New → Database → Redis.
4. Создать **один сервис** (Backend + Frontend в одном контейнере):
   - New → GitHub Repo → выбрать репозиторий.
   - Root Directory не задавать — используется корневой `Dockerfile`.
   - Подключить PostgreSQL (Reference → Variables).
   - Добавить переменные: `OPENAI_API_KEY`, `ADMIN_TOKEN`, `DATABASE_BACKEND=postgres`, `SECRET_ENCRYPTION_KEY`, `CORS_ORIGINS`.
   - `NEXT_PUBLIC_API_URL` и `NEXT_PUBLIC_WS_URL` не нужны — frontend и API на одном домене.
6. Сгенерировать домен (Settings → Networking → Generate Domain).
7. Обновить `CORS_ORIGINS` на URL вашего домена (например `["https://xxx.railway.app"]`).

---

## 7. Схема PostgreSQL (после миграции)

Основные сущности:

- `conversations` — диалоги
- `messages` — сообщения
- `agents` — конфигурация агентов
- `audit_logs` — аудит
- `channel_bindings` — привязки каналов
- `instagram_profiles` — профили Instagram
- `notification_configs` — конфигурация уведомлений
- `rag_documents` — RAG-документы (с полем `embedding` типа vector)

---

## 8. Риски и ограничения

| Риск | Рекомендация |
|------|--------------|
| Cold start | Включить Always-on при необходимости |
| WebSocket | Использовать `wss://` для production |
| Регион | Railway сам выбирает регион; при необходимости можно указать в настройках проекта |

---

## 9. Ссылки

- [Railway — Databases](https://docs.railway.app/guides/databases)
- [Railway — PostgreSQL + pgvector](https://railway.com/deploy/postgres-with-pgvector-engine)
- [Railway — Variables](https://docs.railway.app/reference/variables)
- Репозиторий: [AI-Agents-CRM](https://github.com/progprogect/AI-Agents-CRM)
