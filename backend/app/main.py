from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import check_connection, close_db, init_db
from app.db.seed import seed_all

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if settings.is_development else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle handler.

    On startup:
    * Creates the upload directory if it does not already exist.
    * Initialises the MongoDB connection and registers all Beanie Document
      models via :func:`~app.db.database.init_db`.
    * Seeds default data (LLM profile, agent configs, stage configs) when
      ``AUTO_SEED=true`` (the default).
    * Registers the running event loop on the WebSocket manager so that
      :meth:`~app.api.v1.websocket.ConnectionManager.broadcast_from_thread`
      works even before the first client connects.

    On shutdown:
    * Closes the MongoDB connection via :func:`~app.db.database.close_db`.
    """
    import asyncio

    from app.api.v1.websocket import manager as ws_manager

    logger.info("Starting Auto-AT backend (env=%s)", settings.APP_ENV)

    # ── Upload directory ──────────────────────────────────────────────────
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    logger.info("Upload directory: %s", settings.UPLOAD_DIR)

    # ── MongoDB + Beanie ──────────────────────────────────────────────────
    await init_db()

    # ── Seed default data ─────────────────────────────────────────────────
    if settings.AUTO_SEED:
        await seed_all()

    # ── Recover orphaned runs from previous sessions ───────────────────────
    from app.db.crud import recover_orphaned_runs

    recovered = await recover_orphaned_runs()
    if recovered > 0:
        logger.warning(
            "Recovered %d orphaned pipeline run(s) from the previous session.",
            recovered,
        )
    else:
        logger.info("No orphaned runs found.")

    # ── WebSocket event-loop registration ─────────────────────────────────
    # Register the event loop on the WebSocket manager BEFORE any pipeline
    # background tasks start.  Without this, broadcast_from_thread() drops
    # every event if the pipeline thread fires before the first WS client
    # connects (which sets _loop lazily).
    ws_manager.set_loop(asyncio.get_running_loop())
    logger.info("WebSocket manager event loop registered ✓")

    logger.info("Auto-AT backend ready ✓")

    yield  # ← application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Shutting down Auto-AT backend…")
    await close_db()
    logger.info("Auto-AT backend stopped.")


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance.

    All routers are registered here so that the module-level ``app`` object
    is fully wired up when imported (e.g. by Uvicorn or tests).

    Returns:
        A fully-configured :class:`~fastapi.FastAPI` instance.
    """
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        description=(
            "Auto-AT: Multi-Agent Automated Testing System. "
            "Upload a requirements document and let the AI pipeline generate, "
            "execute, and report on your test suite."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────
    from app.api.v1 import (
        agent_configs,
        chat,
        llm_profiles,
        pipeline,
        pipeline_templates,
        stage_configs,
        websocket,
    )

    # REST API routers – all mounted under /api/v1
    app.include_router(pipeline.router, prefix="/api/v1", tags=["Pipeline"])
    app.include_router(
        pipeline_templates.router,
        prefix="/api/v1",
        tags=["Pipeline Templates"],
    )
    app.include_router(
        llm_profiles.router, prefix="/api/v1", tags=["Admin – LLM Profiles"]
    )
    app.include_router(
        agent_configs.router, prefix="/api/v1", tags=["Admin – Agent Configs"]
    )
    app.include_router(
        stage_configs.router, prefix="/api/v1", tags=["Admin – Stage Configs"]
    )
    app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])

    # WebSocket router – the route itself defines /ws/pipeline/{run_id}
    app.include_router(websocket.router, tags=["WebSocket"])

    return app


app = create_app()


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"], summary="Health check")
async def health_check() -> dict[str, str]:
    """Return application status and a live MongoDB connectivity check.

    Used by Docker health-checks, load balancers, and the frontend to verify
    that the backend is reachable before starting a pipeline run.

    Returns:
        A JSON dict with ``status``, ``version``, ``env``, and ``database``
        keys.  ``status`` is ``"ok"`` when MongoDB responds to a ping,
        ``"degraded"`` otherwise.
    """
    db_ok = await check_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "database": "connected" if db_ok else "unreachable",
    }


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Redirect hint for the API root."""
    return {"message": "Auto-AT API", "docs": "/docs"}


# ── Dev entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.is_development,
        log_level="debug" if settings.is_development else "info",
    )
