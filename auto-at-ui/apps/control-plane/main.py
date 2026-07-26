# Đây là file để chạy fastapi, đồng thời chỉ khai báo route name lớn cho toàn bộ các api
from uuid import UUID, uuid4

from api.v1.router import router as v1_router
from api.v1.routes.health import router as health_router
from config import get_settings
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from infrastructure.observability import metrics, trace_context

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API boundary for multi-agent automation testing.",
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
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = str(context.correlation_id)
    response.headers["traceparent"] = context.traceparent()
    return response
