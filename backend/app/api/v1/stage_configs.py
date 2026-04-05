from __future__ import annotations

"""
api/v1/stage_configs.py – REST endpoints for pipeline stage configuration.

All route handlers are ``async`` and call Beanie CRUD functions directly —
no SQLAlchemy session is needed.  Stage IDs are unique snake_case slugs
(e.g. ``"ingestion"``, ``"testcase"``).

Endpoints:
    GET    /admin/stage-configs              – list all stages
    POST   /admin/stage-configs              – create a custom stage
    GET    /admin/stage-configs/{stage_id}   – get one stage
    PUT    /admin/stage-configs/{stage_id}   – partial update
    DELETE /admin/stage-configs/{stage_id}   – delete a custom stage
    POST   /admin/stage-configs/reorder      – batch reorder
"""

import logging

from fastapi import APIRouter, HTTPException, status

from app.db import crud
from app.db.models import StageConfigDocument
from app.schemas.stage_config import (
    StageConfigCreate,
    StageConfigResponse,
    StageConfigUpdate,
    StageReorderRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/stage-configs", tags=["Admin – Stage Configs"])


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _doc_to_response(doc: StageConfigDocument) -> StageConfigResponse:
    """Convert a Beanie document to the public response schema.

    Coerces the MongoDB ``ObjectId`` to a plain ``str`` for JSON serialisation.

    Args:
        doc: Beanie document from the ``stage_configs`` collection.

    Returns:
        A :class:`~app.schemas.stage_config.StageConfigResponse` instance.
    """
    data = doc.model_dump()
    data["id"] = str(doc.id)
    return StageConfigResponse(**data)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/stage-configs
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[StageConfigResponse],
    summary="List all stage configs",
    description=(
        "Returns every pipeline stage configuration ordered by ``order`` "
        "ascending.  Both built-in and custom stages are included."
    ),
)
async def list_stage_configs() -> list[StageConfigResponse]:
    """Return all stage configurations ordered by execution order.

    Returns:
        List of :class:`~app.schemas.stage_config.StageConfigResponse` objects,
        sorted ascending by ``order``.
    """
    stages = await crud.get_all_stage_configs()
    return [_doc_to_response(s) for s in stages]


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/stage-configs
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=StageConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom stage",
    description=(
        "Creates a new custom (non-builtin) pipeline stage.  "
        "The ``stage_id`` must be a unique snake_case slug (3–50 characters). "
        "Built-in stages are seeded at startup and cannot be created via this "
        "endpoint."
    ),
)
async def create_stage_config(body: StageConfigCreate) -> StageConfigResponse:
    """Create a new custom pipeline stage.

    Args:
        body: Stage creation payload validated by
            :class:`~app.schemas.stage_config.StageConfigCreate`.

    Returns:
        The newly-created :class:`~app.schemas.stage_config.StageConfigResponse`.

    Raises:
        HTTPException: 409 Conflict if a stage with the same ``stage_id``
            already exists.
    """
    existing = await crud.get_stage_config(body.stage_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A stage config with stage_id={body.stage_id!r} already exists "
                f"(id={str(existing.id)})."
            ),
        )

    doc = await crud.create_stage_config(body.model_dump())
    logger.info(
        "[StageConfig] Created stage_id=%r  id=%s  order=%d",
        doc.stage_id,
        str(doc.id),
        doc.order,
    )
    return _doc_to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/stage-configs/reorder  (must be before /{stage_id} to avoid clash)
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/reorder",
    summary="Batch reorder stages",
    description=(
        "Accepts a list of ``{stage_id, order}`` objects and updates the "
        "``order`` field for each matching stage in a single batch operation. "
        "Stages not mentioned in the payload keep their existing order."
    ),
)
async def reorder_stages(body: StageReorderRequest) -> dict[str, str]:
    """Reorder pipeline stages in bulk.

    Args:
        body: List of ``{stage_id, order}`` mappings.

    Returns:
        A simple acknowledgement dict.
    """
    await crud.reorder_stages(body.stages)
    logger.info("[StageConfig] Batch reorder applied  count=%d", len(body.stages))
    return {"message": "Stages reordered successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/stage-configs/{stage_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{stage_id}",
    response_model=StageConfigResponse,
    summary="Get a stage config",
    description="Returns the configuration for a single pipeline stage by its slug.",
)
async def get_stage_config(stage_id: str) -> StageConfigResponse:
    """Retrieve one stage configuration by slug.

    Args:
        stage_id: Unique stage slug such as ``"ingestion"``.

    Returns:
        The matching :class:`~app.schemas.stage_config.StageConfigResponse`.

    Raises:
        HTTPException: 404 if no stage exists for *stage_id*.
    """
    doc = await crud.get_stage_config(stage_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage config with stage_id={stage_id!r} not found.",
        )
    return _doc_to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /admin/stage-configs/{stage_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{stage_id}",
    response_model=StageConfigResponse,
    summary="Update a stage config",
    description=(
        "Partially updates a stage configuration.  Only fields present in the "
        "request body are written; omitted fields keep their current values. "
        "Both built-in and custom stages may be updated."
    ),
)
async def update_stage_config(
    stage_id: str,
    body: StageConfigUpdate,
) -> StageConfigResponse:
    """Partially update a pipeline stage config.

    Args:
        stage_id: Unique stage slug to update.
        body: Partial update payload; only set fields are written.

    Returns:
        The updated :class:`~app.schemas.stage_config.StageConfigResponse`.

    Raises:
        HTTPException: 404 if no stage exists for *stage_id*.
    """
    update_data = body.model_dump(exclude_unset=True)
    doc = await crud.update_stage_config(stage_id, update_data)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage config with stage_id={stage_id!r} not found.",
        )
    logger.info("[StageConfig] Updated stage_id=%r", stage_id)
    return _doc_to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /admin/stage-configs/{stage_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom stage",
    description=(
        "Deletes a custom (non-builtin) stage configuration.  "
        "Built-in stages (ingestion, testcase, execution, reporting) cannot be "
        "deleted — disable them instead by setting ``enabled=false``."
    ),
)
async def delete_stage_config(stage_id: str) -> None:
    """Delete a custom pipeline stage config.

    Args:
        stage_id: Unique stage slug to delete.

    Raises:
        HTTPException: 404 if no stage exists for *stage_id*.
        HTTPException: 403 Forbidden if the stage is a built-in stage.
    """
    doc = await crud.get_stage_config(stage_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage config with stage_id={stage_id!r} not found.",
        )

    try:
        await crud.delete_stage_config(stage_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    logger.info("[StageConfig] Deleted stage_id=%r", stage_id)
