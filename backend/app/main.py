from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import SessionLocal, check_connection, create_tables
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
    """
    Startup / shutdown logic.
    - Creates all DB tables (idempotent).
    - Seeds default data if AUTO_SEED=true.
    - Creates the upload directory if it does not exist.
    """
    logger.info("Starting Auto-AT backend (env=%s)", settings.APP_ENV)

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    logger.info("Upload directory: %s", settings.UPLOAD_DIR)

    # Create DB tables
    logger.info("Initialising database: %s", settings.DATABASE_URL)
    create_tables()
    logger.info("Database tables ready.")

    # Seed default data
    if settings.AUTO_SEED:
        with SessionLocal() as db:
            seed_all(db)

    logger.info("Auto-AT backend ready ✓")

    yield  # ← application runs here

    logger.info("Shutting down Auto-AT backend.")


# ── App factory ───────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
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

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.api.v1 import agent_configs, llm_profiles, pipeline, websocket

    # REST API routers – all mounted under /api/v1
    app.include_router(pipeline.router, prefix="/api/v1", tags=["Pipeline"])
    app.include_router(
        llm_profiles.router, prefix="/api/v1", tags=["Admin – LLM Profiles"]
    )
    app.include_router(
        agent_configs.router, prefix="/api/v1", tags=["Admin – Agent Configs"]
    )

    # WebSocket router – mounted at root (the route itself defines /ws/pipeline/{run_id})
    app.include_router(websocket.router, tags=["WebSocket"])

    return app


app = create_app()


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"], summary="Health check")
def health_check() -> dict[str, str]:
    """
    Returns the application status and a DB connectivity check.
    Used by Docker health-checks, load balancers, and the frontend
    to verify the backend is reachable before starting a pipeline run.
    """
    db_ok = check_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "database": "connected" if db_ok else "unreachable",
    }


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
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
