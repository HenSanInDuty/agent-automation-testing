# Đây là file để chạy fastapi, đồng thời chỉ khai báo route name lớn cho toàn bộ các api
import logging
from uuid import UUID, uuid4

from api.v1.router import router as v1_router
from api.v1.routes.health import router as health_router
from config import get_settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from infrastructure.observability import (
    configure_logging,
    log_event,
    metrics,
    reset_trace_context,
    trace_context,
)

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API boundary for multi-agent automation testing.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.dashboard_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Idempotency-Key",
        "X-Actor-Id",
        "X-Actor-Roles",
        "X-Tenant-Id",
        "X-CSRF-Token",
    ],
)


app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def prometheus_metrics() -> str:
    """Internal scrape endpoint for the self-hosted metrics collector."""
    return metrics.prometheus()


@app.middleware("http")
async def correlation_trace(request: Request, call_next):
    """Propagate correlation data into logs/traces and all HTTP responses."""
    try:
        correlation_id = UUID(request.headers.get("X-Correlation-Id", ""))
    except ValueError:
        correlation_id = uuid4()
    context = trace_context(correlation_id, request.headers.get("traceparent"))
    metrics.increment("api_request")
    try:
        response = await call_next(request)
        log_event(
            logger,
            logging.INFO,
            "api.request.completed",
            "HTTP request completed.",
            status_code=response.status_code,
        )
    except Exception:
        log_event(logger, logging.ERROR, "api.request.failed", "HTTP request failed.")
        response = JSONResponse(status_code=500, content={"detail": "Internal server error."})
    finally:
        reset_trace_context()
    response.headers["X-Correlation-Id"] = str(context.correlation_id)
    response.headers["traceparent"] = context.traceparent()
    return response
