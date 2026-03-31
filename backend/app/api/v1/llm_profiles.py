from __future__ import annotations

import logging
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.db import crud
from app.schemas.llm_profile import (
    LLMProfileCreate,
    LLMProfileInternal,
    LLMProfileListResponse,
    LLMProfileResponse,
    LLMProfileUpdate,
    LLMTestRequest,
    LLMTestResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/llm-profiles", tags=["Admin – LLM Profiles"])

# ─────────────────────────────────────────────────────────────────────────────
# Dependency alias
# ─────────────────────────────────────────────────────────────────────────────

DB = Annotated[Session, Depends(get_db)]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_or_404(db: Session, profile_id: int):
    """Return the LLMProfile ORM object or raise 404."""
    profile = crud.get_llm_profile(db, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id} not found.",
        )
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/llm-profiles
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=LLMProfileListResponse,
    summary="List all LLM profiles",
    description=(
        "Returns a paginated list of all LLM profiles. "
        "API keys are masked in the response."
    ),
)
def list_llm_profiles(
    db: DB,
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
) -> LLMProfileListResponse:
    items, total = crud.get_all_llm_profiles(db, skip=skip, limit=limit)
    return LLMProfileListResponse(
        items=[LLMProfileResponse.model_validate(p) for p in items],
        total=total,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/llm-profiles
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=LLMProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new LLM profile",
)
def create_llm_profile(
    db: DB,
    payload: LLMProfileCreate,
) -> LLMProfileResponse:
    # Prevent duplicate names
    existing = crud.get_llm_profile_by_name(db, payload.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An LLM profile named {payload.name!r} already exists (id={existing.id}).",
        )

    profile = crud.create_llm_profile(db, payload)
    logger.info("[LLM] Created profile id=%d name=%r", profile.id, profile.name)
    return LLMProfileResponse.model_validate(profile)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/llm-profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{profile_id}",
    response_model=LLMProfileResponse,
    summary="Get a single LLM profile",
)
def get_llm_profile(db: DB, profile_id: int) -> LLMProfileResponse:
    profile = _get_or_404(db, profile_id)
    return LLMProfileResponse.model_validate(profile)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /admin/llm-profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{profile_id}",
    response_model=LLMProfileResponse,
    summary="Update an LLM profile (partial update supported)",
    description=(
        "Only fields present in the request body are updated. "
        'To update just the API key, send only `{"api_key": "sk-..."}`. '
        "Setting `is_default=true` automatically clears the flag on all other profiles."
    ),
)
def update_llm_profile(
    db: DB,
    profile_id: int,
    payload: LLMProfileUpdate,
) -> LLMProfileResponse:
    # Check name uniqueness if name is being changed
    if payload.name is not None:
        existing = crud.get_llm_profile_by_name(db, payload.name)
        if existing is not None and existing.id != profile_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Another LLM profile named {payload.name!r} already exists (id={existing.id}).",
            )

    profile = crud.update_llm_profile(db, profile_id, payload)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id} not found.",
        )
    logger.info("[LLM] Updated profile id=%d", profile_id)
    return LLMProfileResponse.model_validate(profile)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /admin/llm-profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an LLM profile",
    description=(
        "Deletes the LLM profile. "
        "Agent configs that referenced this profile will have their `llm_profile_id` "
        "set to NULL (falls back to the global default)."
    ),
)
def delete_llm_profile(db: DB, profile_id: int) -> None:
    deleted = crud.delete_llm_profile(db, profile_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id} not found.",
        )
    logger.info("[LLM] Deleted profile id=%d", profile_id)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/llm-profiles/{id}/set-default
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{profile_id}/set-default",
    response_model=LLMProfileResponse,
    summary="Set a profile as the global default",
    description=(
        "Marks this profile as `is_default=true` and clears the flag "
        "on all other profiles. The global default is used by any agent "
        "that does not have its own `llm_profile_id` override."
    ),
)
def set_default_llm_profile(db: DB, profile_id: int) -> LLMProfileResponse:
    profile = crud.set_default_llm_profile(db, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id} not found.",
        )
    logger.info("[LLM] Set profile id=%d as global default", profile_id)
    return LLMProfileResponse.model_validate(profile)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/llm-profiles/{id}/test
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{profile_id}/test",
    response_model=LLMTestResponse,
    summary="Test LLM profile connectivity",
    description=(
        "Sends a lightweight prompt to the configured LLM and measures latency. "
        "Returns `success=true` if the LLM responds within the timeout window. "
        "Useful for validating API keys and base URLs before running a pipeline."
    ),
)
def test_llm_profile(
    db: DB,
    profile_id: int,
    body: Annotated[LLMTestRequest, Body()] = LLMTestRequest(),
) -> LLMTestResponse:
    profile = _get_or_404(db, profile_id)

    # Build an internal schema (exposes real api_key)
    internal = LLMProfileInternal.model_validate(profile)

    if not internal.api_key and internal.provider.requires_api_key:
        return LLMTestResponse(
            success=False,
            message=(
                f"Profile '{internal.name}' has no API key configured. "
                "Please add an API key before testing."
            ),
        )

    try:
        from app.core.llm_factory import build_llm

        llm = build_llm(internal)
    except Exception as exc:
        logger.warning(
            "[LLM] Failed to build LLM for profile id=%d: %s", profile_id, exc
        )
        return LLMTestResponse(
            success=False,
            message=f"Failed to initialise LLM client: {exc}",
        )

    # Attempt the test call
    start_ms = int(time.monotonic() * 1000)
    try:
        import asyncio
        import inspect

        result = llm.call(body.prompt)

        # llm.call might return a coroutine on some implementations
        if inspect.iscoroutine(result):
            result = asyncio.get_event_loop().run_until_complete(result)

        latency_ms = int(time.monotonic() * 1000) - start_ms
        response_text = str(result).strip() if result else ""

        logger.info(
            "[LLM] Test OK profile id=%d latency=%dms preview=%r",
            profile_id,
            latency_ms,
            response_text[:80],
        )
        return LLMTestResponse(
            success=True,
            message="LLM connection successful.",
            response_preview=response_text[:300],
            latency_ms=latency_ms,
        )

    except Exception as exc:
        latency_ms = int(time.monotonic() * 1000) - start_ms
        logger.warning(
            "[LLM] Test FAILED profile id=%d latency=%dms error=%s",
            profile_id,
            latency_ms,
            exc,
        )
        return LLMTestResponse(
            success=False,
            message=f"LLM call failed: {exc}",
            latency_ms=latency_ms,
        )
