"""FastAPI application entry point.

This is the main entry point for the Agent API.
Storage: PostgreSQL (primary) + Redis (cache/queues).
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.exceptions import AgentException, NotFoundError
from app.api.middleware import (
    LoggingMiddleware,
    RequestIDMiddleware,
    RateLimitMiddleware,
)
from app.config import get_settings
from app.utils.logging_config import setup_logging, get_logger
from app.api.v1 import chat, agents, admin, channel_bindings, instagram, telegram, rag
from app.api.v1 import instagram_test, whatsapp_test, debug, webhook_test, webhook_events, notifications
from app.api.v1 import auth_router, crm, whatsapp, twilio_whatsapp, media
from app.api.v1 import payments
from app.api.v1 import internal
from app.api.v1 import questionnaires
from app.api import websocket, admin_websocket

# Setup logging
settings = get_settings()
setup_logging(
    level="DEBUG" if settings.debug else "INFO",
    json_format=settings.environment == "production",
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    settings = get_settings()
    logger.info(
        "Application starting",
        extra={
            "app_name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )
    # Initialize PostgreSQL pool
    from app.storage.postgres import get_pool
    await get_pool()
    logger.info("PostgreSQL connection pool initialized")

    # Initialize LangGraph checkpointer (workflow state persistence)
    db_url = settings.get_database_url()
    if db_url:
        from app.storage.postgres_checkpointer import init_checkpointer
        await init_checkpointer(db_url)
    else:
        logger.warning(
            "DATABASE_URL not set — LangGraph checkpointer not initialised; "
            "workflow state will be in-memory only"
        )
    # Clear all caches on startup to ensure fresh state
    from app.storage.resolver import get_secrets_manager
    from app.utils.openai_client import get_llm_factory

    secrets_manager = get_secrets_manager()
    if hasattr(secrets_manager, "clear_cache"):
        secrets_manager.clear_cache()

    llm_factory = get_llm_factory()
    llm_factory.clear_cache()

    logger.info("All caches cleared on startup")

    from app.services.user_reminder_scheduler import run_user_reminder_poll_loop
    from app.services.agent_reply_coordinator import (
        run_debounce_poll_loop,
        run_timer_poll_loop,
        run_auto_step_poll_loop,
    )

    shutdown_event = asyncio.Event()

    # Workflow timer poll loop — always started, independent of debounce.
    timer_task = asyncio.create_task(run_timer_poll_loop(shutdown_event))

    # Auto-step poll loop — always started, fires scheduled auto-steps.
    auto_step_task = asyncio.create_task(run_auto_step_poll_loop(shutdown_event))

    # User reminders (Telegram) — scheduled in Postgres + Redis ZSET.
    user_reminder_task = asyncio.create_task(run_user_reminder_poll_loop(shutdown_event))

    debounce_task: Optional[asyncio.Task] = None
    if settings.agent_reply_debounce_seconds > 0:
        debounce_task = asyncio.create_task(run_debounce_poll_loop(shutdown_event))

    yield
    # Shutdown
    shutdown_event.set()
    await timer_task
    await auto_step_task
    await user_reminder_task
    if debounce_task is not None:
        await debounce_task
    from app.storage.postgres_checkpointer import close_checkpointer
    await close_checkpointer()
    from app.storage.postgres import close_pool
    await close_pool()
    logger.info("PostgreSQL connection pool closed")
    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI Agent - MVP API",
        lifespan=lifespan,
    )

    # Request ID middleware (must be first)
    app.add_middleware(RequestIDMiddleware)

    # Rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute
    )

    # Logging middleware
    app.add_middleware(LoggingMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    @app.exception_handler(NotFoundError)
    async def not_found_exception_handler(
        request: Request, exc: NotFoundError
    ):
        """Handle NotFoundError subclasses → HTTP 404."""
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            f"NotFound: {exc.code} - {exc.message}",
            extra={"request_id": request_id, "code": exc.code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(AgentException)
    async def agent_exception_handler(
        request: Request, exc: AgentException
    ):
        """Handle custom AgentException → HTTP 400."""
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            f"AgentException: {exc.code} - {exc.message}",
            extra={
                "request_id": request_id,
                "code": exc.code,
                "details": exc.details,
                "path": request.url.path,
                "method": request.method,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle Pydantic validation errors."""
        request_id = getattr(request.state, "request_id", None)
        # Pydantic v2 / FastAPI can put non-JSON objects into ``input`` and
        # ``ctx`` (e.g. raw Pydantic models, Python exceptions).  Strip them
        # manually so the response stays JSON-serialisable on every version.
        safe_errors = [
            {k: v for k, v in e.items() if k not in ("input", "ctx", "url")}
            for e in exc.errors()
        ]
        logger.warning(
            f"Validation error: {safe_errors}",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "errors": safe_errors,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": safe_errors},
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions."""
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            f"Unhandled exception: {type(exc).__name__} - {str(exc)}",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "exception_type": type(exc).__name__,
            },
        )

        # Don't expose internal error details in production
        settings = get_settings()
        error_message = (
            str(exc) if settings.debug else "An internal error occurred"
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": error_message,
                    "details": {},
                    "request_id": request_id,
                }
            },
        )

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
        }

    # API routes
    # Auth routes (public — no auth required)
    app.include_router(auth_router.router, prefix="/api/v1/admin/auth", tags=["auth"])

    # Register more specific routes first to avoid conflicts
    app.include_router(
        channel_bindings.router, prefix="/api/v1", tags=["channel-bindings"]
    )
    app.include_router(instagram.router, prefix="/api/v1", tags=["instagram"])
    app.include_router(telegram.router, prefix="/api/v1", tags=["telegram"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
    app.include_router(rag.router, prefix="/api/v1/agents", tags=["rag"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(crm.router, prefix="/api/v1/crm", tags=["crm"])
    app.include_router(whatsapp.router, prefix="/api/v1", tags=["whatsapp"])
    app.include_router(twilio_whatsapp.router, prefix="/api/v1", tags=["twilio-whatsapp"])
    app.include_router(media.router, prefix="/api/v1", tags=["media"])
    app.include_router(notifications.router, prefix="/api/v1/admin", tags=["notifications"])
    app.include_router(questionnaires.router, prefix="/api/v1/admin", tags=["questionnaires"])
    app.include_router(payments.router, prefix="/api/v1", tags=["payments"])
    app.include_router(debug.router, prefix="/api/v1", tags=["debug"])
    app.include_router(internal.router, prefix="/api/v1", tags=["internal"])
    app.include_router(instagram_test.router, prefix="/api/v1", tags=["instagram-test"])
    app.include_router(whatsapp_test.router, prefix="/api/v1", tags=["whatsapp-test"])
    app.include_router(webhook_test.router, prefix="/api/v1", tags=["webhook-test"])
    app.include_router(webhook_events.router, prefix="/api/v1", tags=["webhook-events"])

    # WebSocket routes
    app.include_router(websocket.router, tags=["websocket"])
    app.include_router(admin_websocket.router, tags=["admin-websocket"])

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )

