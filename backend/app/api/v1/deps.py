"""
api/v1/deps.py – Shared FastAPI dependencies.

With Beanie as the ODM, there is no per-request Session object to manage.
Beanie operates against the global Motor client that is initialised once at
startup via :func:`app.db.database.init_db`.

This module provides:
- :func:`get_settings`      – injects the cached Settings instance.
- :func:`require_db`        – raises 503 when MongoDB is unreachable.
- :func:`get_current_user`  – validates JWT and returns the UserDocument.
- :func:`require_admin`     – restrict to ADMIN role.
- :func:`require_not_qa`    – restrict to ADMIN or DEV (QA cannot call LLM chat).
- :func:`require_not_dev`   – restrict to ADMIN or QA (DEV cannot create pipelines).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.config import Settings
from app.config import get_settings as _get_settings
from app.db.database import check_connection

# ─────────────────────────────────────────────────────────────────────────────
# Settings dependency
# ─────────────────────────────────────────────────────────────────────────────


async def get_settings() -> Settings:
    """FastAPI dependency that returns the cached application settings."""
    return _get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# DB health guard
# ─────────────────────────────────────────────────────────────────────────────


async def require_db() -> None:
    """FastAPI dependency that aborts with ``503`` when MongoDB is unreachable.

    Raises:
        HTTPException: 503 Service Unavailable if the MongoDB ping fails.
    """
    if not await check_connection():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is currently unavailable. Please try again later.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# JWT / Auth dependencies
# ─────────────────────────────────────────────────────────────────────────────

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(_oauth2_scheme)):  # type: ignore[type-arg]
    """Validate JWT and return the authenticated UserDocument.

    Raises:
        HTTPException: 401 if token is missing, invalid, or user not found.
    """
    from app.db.models import UserDocument
    from app.services.auth_service import decode_access_token

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        username: str = payload.get("sub", "")
        if not username:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = await UserDocument.find_one(UserDocument.username == username)
    if user is None:
        raise credentials_exc
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled.")
    return user


async def require_admin(current_user=Depends(get_current_user)):  # type: ignore[type-arg]
    """Require ADMIN role."""
    from app.db.models import UserRole

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user


async def require_not_qa(current_user=Depends(get_current_user)):  # type: ignore[type-arg]
    """Allow ADMIN and DEV — deny QA (cannot use LLM chat)."""
    from app.db.models import UserRole

    if current_user.role == UserRole.QA:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="QA role cannot access LLM chat.")
    return current_user


async def require_not_dev(current_user=Depends(get_current_user)):  # type: ignore[type-arg]
    """Allow ADMIN and QA — deny DEV (cannot create pipeline templates)."""
    from app.db.models import UserRole

    if current_user.role == UserRole.DEV:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dev role cannot create pipeline templates.")
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
# Convenience type aliases
# ─────────────────────────────────────────────────────────────────────────────

SettingsDep = Annotated[Settings, Depends(get_settings)]
RequireDB = Annotated[None, Depends(require_db)]
