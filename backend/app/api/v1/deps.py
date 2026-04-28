"""
api/v1/deps.py – Shared FastAPI dependencies.

With Beanie as the ODM, there is no per-request Session object to manage.
Beanie operates against the global Motor client that is initialised once at
startup via :func:`app.db.database.init_db`.

This module still provides:
- :func:`get_settings` – injects the cached :class:`~app.config.Settings` instance.
- :func:`require_db` – lightweight guard that raises ``503`` when MongoDB is
  unreachable (useful for endpoints that must abort gracefully rather than
  propagate a Motor connection error deep in the call stack).

Usage::

    @router.get("/items")
    async def list_items(settings: Annotated[Settings, Depends(get_settings)]):
        ...

    @router.post("/runs")
    async def create_run(_: Annotated[None, Depends(require_db)]):
        ...
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.config import Settings
from app.config import get_settings as _get_settings
from app.db.database import check_connection

# ─────────────────────────────────────────────────────────────────────────────
# Settings dependency
# ─────────────────────────────────────────────────────────────────────────────


async def get_settings() -> Settings:
    """FastAPI dependency that returns the cached application settings.

    Because :func:`~app.config.get_settings` is decorated with
    ``@lru_cache``, this is effectively a zero-cost call after the first
    invocation.

    Returns:
        The singleton :class:`~app.config.Settings` instance.
    """
    return _get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# DB health guard
# ─────────────────────────────────────────────────────────────────────────────


async def require_db() -> None:
    """FastAPI dependency that aborts with ``503`` when MongoDB is unreachable.

    Inject this dependency into any endpoint where a database failure should
    surface as a clean HTTP error rather than an unhandled exception::

        @router.post("/runs")
        async def create_run(_: Annotated[None, Depends(require_db)]):
            ...

    Raises:
        HTTPException: 503 Service Unavailable if the MongoDB ping fails.
    """
    if not await check_connection():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is currently unavailable. Please try again later.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Convenience type aliases (use with Annotated for cleaner signatures)
# ─────────────────────────────────────────────────────────────────────────────

SettingsDep = Annotated[Settings, Depends(get_settings)]
"""Type alias for injecting :class:`~app.config.Settings` into route handlers."""

RequireDB = Annotated[None, Depends(require_db)]
"""Type alias for the DB availability guard dependency."""
