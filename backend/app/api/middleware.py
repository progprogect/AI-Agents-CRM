"""Middleware for request processing."""

import asyncio
import time
import uuid
import logging
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add request ID to request and response."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time)

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response."""
        request_id = getattr(request.state, "request_id", None)
        start_time = time.time()

        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
            },
        )

        response = await call_next(request)

        process_time = time.time() - start_time

        logger.info(
            f"Response: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time,
            },
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-process rate limiting middleware (sliding window per IP).

    Uses asyncio.Lock to prevent race conditions in concurrent async requests.
    For multi-process deployments, use a shared Redis-backed rate limiter instead.
    """

    def __init__(self, app, requests_per_minute: int = 60):
        """Initialize rate limiter."""
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limit."""
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()

        async with self._lock:
            # Remove timestamps older than 1 minute (sliding window)
            window = self.request_counts.get(client_ip, [])
            window = [t for t in window if current_time - t < 60]

            if len(window) >= self.requests_per_minute:
                logger.warning(
                    f"Rate limit exceeded for {client_ip}",
                    extra={
                        "client_ip": client_ip,
                        "path": request.url.path,
                        "request_id": getattr(request.state, "request_id", None),
                    },
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Too many requests. Please try again later.",
                        }
                    },
                )

            window.append(current_time)
            self.request_counts[client_ip] = window

        return await call_next(request)
