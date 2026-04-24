from __future__ import annotations

"""
api/v1/llm_profiles.py – REST endpoints for LLM profile administration.

All route handlers are ``async`` and call Beanie CRUD functions directly —
no SQLAlchemy session is needed.  Profile IDs are MongoDB ObjectId hex strings.

Endpoints:
    GET    /admin/llm-profiles              – paginated list
    POST   /admin/llm-profiles              – create
    GET    /admin/llm-profiles/{id}         – get one
    PUT    /admin/llm-profiles/{id}         – partial update
    DELETE /admin/llm-profiles/{id}         – delete
    POST   /admin/llm-profiles/{id}/set-default   – set as global default
    POST   /admin/llm-profiles/{id}/test    – test LLM connectivity
"""

import logging
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Body, HTTPException, Query, status

from app.db import crud
from app.db.models import LLMProfileDocument
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
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_or_404(profile_id: str) -> LLMProfileDocument:
    """Fetch an LLM profile by ObjectId string, or raise HTTP 404.

    Args:
        profile_id: MongoDB ObjectId hex string.

    Returns:
        The matching :class:`~app.db.models.LLMProfileDocument`.

    Raises:
        HTTPException: 404 if no document exists for *profile_id*.
    """
    doc = await crud.get_llm_profile(profile_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id!r} not found.",
        )
    return doc


def _doc_to_response(doc: LLMProfileDocument) -> LLMProfileResponse:
    """Convert a Beanie document to the safe public response schema.

    The ``model_validator`` on :class:`~app.schemas.llm_profile.LLMProfileResponse`
    handles API-key masking and ObjectId → str coercion automatically.

    Args:
        doc: Beanie document from the ``llm_profiles`` collection.

    Returns:
        A :class:`~app.schemas.llm_profile.LLMProfileResponse` with the
        ``api_key`` field masked.
    """
    return LLMProfileResponse.model_validate(doc)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/llm-profiles
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=LLMProfileListResponse,
    summary="List all LLM profiles",
    description=(
        "Returns a paginated list of all LLM profiles. "
        "API keys are masked in the response."
    ),
)
async def list_llm_profiles(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
) -> LLMProfileListResponse:
    """Return a paginated list of all LLM profiles.

    Args:
        skip: Number of documents to skip (offset).
        limit: Maximum number of documents to return.

    Returns:
        :class:`~app.schemas.llm_profile.LLMProfileListResponse` with masked
        API keys and the unfiltered total count.
    """
    items, total = await crud.get_all_llm_profiles(skip=skip, limit=limit)
    return LLMProfileListResponse(
        items=[_doc_to_response(p) for p in items],
        total=total,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/llm-profiles
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=LLMProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new LLM profile",
)
async def create_llm_profile(
    payload: LLMProfileCreate,
) -> LLMProfileResponse:
    """Create a new LLM profile.

    Names must be unique across all profiles.  When ``is_default=true`` the
    existing default profile (if any) is automatically unset.

    Args:
        payload: Profile creation payload validated by
            :class:`~app.schemas.llm_profile.LLMProfileCreate`.

    Returns:
        The newly-created profile with a masked API key.

    Raises:
        HTTPException: 409 Conflict if a profile with the same name already
            exists.
    """
    existing = await crud.get_llm_profile_by_name(payload.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An LLM profile named {payload.name!r} already exists "
                f"(id={str(existing.id)})."
            ),
        )

    # Normalise enum → string value so the plain dict is safe to store
    data = payload.model_dump()
    if hasattr(data.get("provider"), "value"):
        data["provider"] = data["provider"].value

    doc = await crud.create_llm_profile(data)
    logger.info("[LLM] Created profile id=%s name=%r", str(doc.id), doc.name)
    return _doc_to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/llm-profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{profile_id}",
    response_model=LLMProfileResponse,
    summary="Get a single LLM profile",
)
async def get_llm_profile(profile_id: str) -> LLMProfileResponse:
    """Retrieve a single LLM profile by its MongoDB ObjectId.

    Args:
        profile_id: Hex string of the MongoDB ObjectId.

    Returns:
        The matching profile with a masked API key.

    Raises:
        HTTPException: 404 if the profile does not exist.
    """
    doc = await _get_or_404(profile_id)
    return _doc_to_response(doc)


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
        "Setting `is_default=true` automatically clears the flag on all other "
        "profiles."
    ),
)
async def update_llm_profile(
    profile_id: str,
    payload: LLMProfileUpdate,
) -> LLMProfileResponse:
    """Partially update an LLM profile.

    Only the fields present in *payload* are written; omitted fields keep
    their existing values.

    Args:
        profile_id: Hex string of the MongoDB ObjectId to update.
        payload: Partial update payload.

    Returns:
        The updated profile with a masked API key.

    Raises:
        HTTPException: 404 if the profile does not exist.
        HTTPException: 409 Conflict if the new name is already taken by
            another profile.
    """
    update_data = payload.model_dump(exclude_unset=True)

    # Enforce name uniqueness when name is being changed
    if "name" in update_data:
        existing = await crud.get_llm_profile_by_name(update_data["name"])
        if existing is not None and str(existing.id) != profile_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Another LLM profile named {update_data['name']!r} already "
                    f"exists (id={str(existing.id)})."
                ),
            )

    # Normalise provider enum → string
    if "provider" in update_data and hasattr(update_data["provider"], "value"):
        update_data["provider"] = update_data["provider"].value

    doc = await crud.update_llm_profile(profile_id, update_data)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id!r} not found.",
        )

    logger.info("[LLM] Updated profile id=%s", profile_id)
    return _doc_to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /admin/llm-profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an LLM profile",
    description=(
        "Deletes the LLM profile. Agent configs that referenced this profile "
        "will fall back to the global default on their next pipeline run."
    ),
)
async def delete_llm_profile(profile_id: str) -> None:
    """Delete an LLM profile by ObjectId.

    Args:
        profile_id: Hex string of the MongoDB ObjectId.

    Raises:
        HTTPException: 404 if the profile does not exist.
    """
    deleted = await crud.delete_llm_profile(profile_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id!r} not found.",
        )
    logger.info("[LLM] Deleted profile id=%s", profile_id)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/llm-profiles/{id}/set-default
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{profile_id}/set-default",
    response_model=LLMProfileResponse,
    summary="Set a profile as the global default",
    description=(
        "Marks this profile as ``is_default=true`` and clears the flag on all "
        "other profiles.  The global default is used by any agent that does not "
        "have its own ``llm_profile_id`` override."
    ),
)
async def set_default_llm_profile(profile_id: str) -> LLMProfileResponse:
    """Promote a profile to the global default.

    Args:
        profile_id: Hex string of the MongoDB ObjectId to promote.

    Returns:
        The updated profile (now ``is_default=True``).

    Raises:
        HTTPException: 404 if the profile does not exist.
    """
    doc = await crud.set_default_llm_profile(profile_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM profile with id={profile_id!r} not found.",
        )
    logger.info("[LLM] Set profile id=%s as global default", profile_id)
    return _doc_to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/llm-profiles/{id}/test
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{profile_id}/test",
    response_model=LLMTestResponse,
    summary="Test LLM profile connectivity",
    description=(
        "Sends a lightweight prompt to the configured LLM and measures latency. "
        "Returns ``success=true`` if the LLM responds within the timeout window. "
        "Useful for validating API keys and base URLs before running a pipeline."
    ),
)
async def test_llm_profile(
    profile_id: str,
    body: Annotated[LLMTestRequest, Body()] = LLMTestRequest(),
) -> LLMTestResponse:
    """Fire a test prompt at the configured LLM and report latency.

    Args:
        profile_id: Hex string of the MongoDB ObjectId.
        body: Optional test-prompt override and timeout.

    Returns:
        :class:`~app.schemas.llm_profile.LLMTestResponse` indicating success
        or failure with a response preview and latency in milliseconds.

    Raises:
        HTTPException: 404 if the profile does not exist.
    """
    doc = await _get_or_404(profile_id)

    # Build an internal schema that exposes the real api_key
    internal = LLMProfileInternal.model_validate(doc)

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
            "[LLM] Failed to build LLM for profile id=%s: %s", profile_id, exc
        )
        return LLMTestResponse(
            success=False,
            message=f"Failed to initialise LLM client: {exc}",
        )

    start_ms = int(time.monotonic() * 1000)
    try:
        import asyncio
        import inspect

        result = llm.call(body.prompt)

        # llm.call may return a coroutine on some LiteLLM backends
        if inspect.iscoroutine(result):
            result = await asyncio.ensure_future(result)

        latency_ms = int(time.monotonic() * 1000) - start_ms
        response_text = str(result).strip() if result else ""

        logger.info(
            "[LLM] Test OK profile id=%s latency=%dms preview=%r",
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
            "[LLM] Test FAILED profile id=%s latency=%dms error=%s",
            profile_id,
            latency_ms,
            exc,
        )
        return LLMTestResponse(
            success=False,
            message=f"LLM call failed: {exc}",
            latency_ms=latency_ms,
        )
