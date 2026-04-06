"""
db/database.py – MongoDB connection management using pymongo async + Beanie 2.x.

Usage::

    from app.db.database import init_db, close_db

    # In FastAPI lifespan:
    await init_db()
    yield
    await close_db()

The module keeps a single private ``AsyncMongoClient`` instance for the
entire process lifetime.  :func:`init_db` must be called once at application
startup (before any DB operations).  :func:`close_db` should be called on
shutdown to gracefully release the connection pool.

Note: Beanie 2.x dropped Motor in favour of the native pymongo async driver
(``pymongo.asynchronous``).  We therefore use ``AsyncMongoClient`` directly
instead of the Motor wrapper.
"""

from __future__ import annotations

import logging
from typing import Optional

from beanie import init_beanie
from pymongo.asynchronous.mongo_client import AsyncMongoClient

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level pymongo async client — None until init_db() is called.
_client: Optional[AsyncMongoClient] = None  # type: ignore[type-arg]


async def init_db() -> None:
    """Initialise the MongoDB connection and register all Beanie Document models.

    This function must be awaited exactly once during application startup
    (e.g. inside the FastAPI ``lifespan`` context manager) before any
    coroutine performs a database operation.

    The function is idempotent with respect to Beanie — if ``init_beanie``
    has already been called, Motor will simply reuse the existing connection
    pool.

    Raises:
        motor.motor_asyncio.MotorConnectionFailure: If MongoDB is unreachable.
    """
    global _client

    # Local imports avoid circular dependency at module load time; these
    # models are only needed once Beanie is being initialised.
    from app.db.models import (
        AgentConfigDocument,
        LLMProfileDocument,
        PipelineResultDocument,
        PipelineRunDocument,
        PipelineTemplateDocument,
        StageConfigDocument,
    )

    logger.info(
        "Connecting to MongoDB: %s / %s",
        settings.MONGODB_URI,
        settings.MONGODB_DB_NAME,
    )

    _client = AsyncMongoClient(settings.MONGODB_URI)
    db = _client[settings.MONGODB_DB_NAME]

    await init_beanie(
        database=db,
        document_models=[
            LLMProfileDocument,
            AgentConfigDocument,
            StageConfigDocument,
            PipelineRunDocument,
            PipelineResultDocument,
            PipelineTemplateDocument,  # NEW V3
        ],
    )

    logger.info("MongoDB + Beanie initialized ✓")


async def close_db() -> None:
    """Close the active MongoDB connection pool.

    Safe to call even if :func:`init_db` was never called (no-op in that
    case).  After this returns, any further DB operation will raise an error
    until :func:`init_db` is called again.
    """
    global _client

    if _client is not None:
        await _client.close()
        _client = None
        logger.info("MongoDB connection closed.")
    else:
        logger.debug("close_db() called but no active client — skipping.")


async def check_connection() -> bool:
    """Perform a lightweight MongoDB ping and return ``True`` if successful.

    Used by the ``/health`` endpoint and by monitoring infrastructure to
    verify that the database is reachable without performing a full query.

    Returns:
        ``True``  – MongoDB responded to the ``ping`` command.
        ``False`` – The client is not initialised, or the ping timed out /
                    raised an exception.
    """
    global _client

    if _client is None:
        logger.debug("check_connection(): no active client.")
        return False

    try:
        await _client.admin.command("ping")  # type: ignore[union-attr]
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("MongoDB health-check failed: %s", exc)
        return False
