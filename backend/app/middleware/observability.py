"""
middleware/observability.py – HTTP request telemetry → Kafka ``api_requests`` topic.

Captures per-request metadata and emits it fire-and-forget to Kafka.
All failures are silently swallowed so the middleware never disrupts normal
request processing.

Fields emitted (see ClickHouse ``api_requests`` table):
    method          – HTTP verb (GET / POST / …)
    path            – URL path, query-params stripped
    status_code     – Response HTTP status code
    duration_ms     – Wall-clock time from first byte received to response sent
    client_ip       – X-Forwarded-For (first value) or remote addr
    user_agent      – User-Agent request header
    request_id      – X-Request-ID header if present, else auto-generated UUID4
    content_length  – Response Content-Length header (–1 when unknown)
    + common debug fields: timestamp, app_version, env, hostname, pid
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Paths skipped to reduce noise (health checks, docs, root)
_SKIP_PATHS = frozenset({
    "/health",
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
})


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that emits one Kafka ``api_requests`` event per HTTP
    request, plus forwards (or generates) an ``X-Request-ID`` header.

    The middleware is intentionally lightweight:
    * Skips static/health paths (``_SKIP_PATHS``).
    * Uses ``await event_bus.emit()`` in the same request coroutine so the
      timestamp is accurate.
    * Any exception in the Kafka path is caught and logged at DEBUG level.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        path = request.url.path

        # Skip low-signal paths
        if path in _SKIP_PATHS or path.startswith("/static"):
            return await call_next(request)

        start = time.monotonic()

        # Extract / generate a correlation ID for distributed tracing
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        response = await call_next(request)

        duration_ms = int((time.monotonic() - start) * 1000)

        # Prefer X-Forwarded-For for real client IP behind proxies
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "")
        )

        # Content-Length from response headers (–1 when streaming/unknown)
        content_length = int(response.headers.get("content-length", -1))

        try:
            from app.services.event_bus import event_bus

            await event_bus.emit(
                "api_requests",
                {
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "user_agent": request.headers.get("user-agent", ""),
                    "request_id": request_id,
                    "content_length": content_length,
                },
            )
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            logger.debug("[Observability] Failed to emit api_request: %s", exc)

        # Propagate the request-id back so callers can correlate logs
        response.headers["x-request-id"] = request_id
        return response
