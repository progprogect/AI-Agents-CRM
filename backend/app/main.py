"""FastAPI application entry point.

This is the main entry point for the Doctor Agent API.
Supports PostgreSQL or DynamoDB backend for storage, cache, and RAG.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.exceptions import DoctorAgentException
from app.api.middleware import (
    LoggingMiddleware,
    RequestIDMiddleware,
    RateLimitMiddleware,
)
from app.config import get_settings
from app.utils.logging_config import setup_logging, get_logger
from app.api.v1 import chat, agents, admin, channel_bindings, instagram, telegram
from app.api.v1 import instagram_test, debug, webhook_test, webhook_events, notifications
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
            "database_backend": settings.database_backend,
        },
    )
    # Initialize PostgreSQL pool when using postgres backend
    if settings.database_backend == "postgres":
        from app.storage.postgres import get_pool
        await get_pool()
        logger.info("PostgreSQL connection pool initialized")
    # Clear all caches on startup to ensure fresh state
    from app.storage.resolver import get_secrets_manager
    from app.utils.openai_client import get_llm_factory

    secrets_manager = get_secrets_manager()
    if hasattr(secrets_manager, "clear_cache"):
        secrets_manager.clear_cache()

    llm_factory = get_llm_factory()
    llm_factory.clear_cache()

    logger.info("All caches cleared on startup")
    yield
    # Shutdown
    if settings.database_backend == "postgres":
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
        description="AI Agent for Doctor - MVP API",
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
    @app.exception_handler(DoctorAgentException)
    async def doctor_agent_exception_handler(
        request: Request, exc: DoctorAgentException
    ):
        """Handle custom DoctorAgentException."""
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            f"DoctorAgentException: {exc.code} - {exc.message}",
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
        logger.warning(
            f"Validation error: {exc.errors()}",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "errors": exc.errors(),
            },
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
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
    # Register more specific routes first to avoid conflicts
    app.include_router(
        channel_bindings.router, prefix="/api/v1", tags=["channel-bindings"]
    )
    app.include_router(instagram.router, prefix="/api/v1", tags=["instagram"])
    app.include_router(telegram.router, prefix="/api/v1", tags=["telegram"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(notifications.router, prefix="/api/v1/admin", tags=["notifications"])
    app.include_router(debug.router, prefix="/api/v1", tags=["debug"])
    app.include_router(instagram_test.router, prefix="/api/v1", tags=["instagram-test"])
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

