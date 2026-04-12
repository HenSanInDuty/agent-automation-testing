from __future__ import annotations

"""
api/v1/stage_configs.py – Stage Config CRUD endpoints (restored in V4).

Stages are now purely organizational — they group agents in the Admin UI
and the Pipeline Builder sidebar. They are NOT used for pipeline execution
order (that's handled by DAG templates).

Endpoints:
    GET    /admin/stage-configs               – list all stages
    GET    /admin/stage-configs/{stage_id}    – get one stage
    POST   /admin/stage-configs               – create custom stage
    PUT    /admin/stage-configs/{stage_id}    – update a stage
    DELETE /admin/stage-configs/{stage_id}    – delete custom stage (reassigns agents)
    POST   /admin/stage-configs/reorder       – reorder stages
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.db import crud
from app.schemas.stage_config import (
    StageConfigCreate,
    StageConfigResponse,
    StageConfigUpdate,
    StageReorderRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/stage-configs",
    tags=["Admin – Stage Configs"],
)

# Built-in stage IDs that cannot be recreated (but CAN be updated)
BUILTIN_STAGE_IDS = {"ingestion", "testcase", "execution", "reporting", "custom"}


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────


def _to_response(stage, agent_count: int = 0) -> StageConfigResponse:
    """Convert a StageConfigDocument to the API response schema."""
    return StageConfigResponse(
        id=str(stage.id),
        stage_id=stage.stage_id,
        display_name=stage.display_name,
        description=stage.description,
        order=stage.order,
        color=stage.color,
        icon=stage.icon,
        enabled=stage.enabled,
        is_builtin=stage.is_builtin,
        agent_count=agent_count,
        created_at=stage.created_at.isoformat(),
        updated_at=stage.updated_at.isoformat(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/stage-configs
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[StageConfigResponse],
    summary="List all stage configs",
    description=(
        "Returns all stage configs sorted by ``order``. "
        "Pass ``enabled_only=true`` to include only enabled stages. "
        "Each entry includes a computed ``agent_count`` field."
    ),
)
async def list_stage_configs(
    enabled_only: bool = Query(
        default=False,
        description="Return only enabled stages",
    ),
) -> list[StageConfigResponse]:
    """List all stage configs with agent counts."""
    stages = await crud.get_all_stage_configs(enabled_only=enabled_only)
    result = []
    for stage in stages:
        count = await crud.count_agents_by_stage(stage.stage_id)
        result.append(_to_response(stage, agent_count=count))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/stage-configs/reorder  ← must be BEFORE /{stage_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/reorder",
    response_model=list[StageConfigResponse],
    summary="Reorder stages",
    description=(
        "Provide an ordered list of ``stage_ids``. "
        "Position in the list determines display order."
    ),
)
async def reorder_stages(body: StageReorderRequest) -> list[StageConfigResponse]:
    """Reorder stages by position in the provided list."""
    stages = await crud.reorder_stages(body.stage_ids)
    result = []
    for stage in stages:
        count = await crud.count_agents_by_stage(stage.stage_id)
        result.append(_to_response(stage, agent_count=count))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/stage-configs/{stage_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{stage_id}",
    response_model=StageConfigResponse,
    summary="Get a stage config by stage_id",
)
async def get_stage_config(stage_id: str) -> StageConfigResponse:
    """Get a single stage config."""
    stage = await crud.get_stage_config(stage_id)
    if stage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage '{stage_id}' not found.",
        )
    count = await crud.count_agents_by_stage(stage_id)
    return _to_response(stage, agent_count=count)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/stage-configs
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=StageConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new custom stage",
)
async def create_stage_config(body: StageConfigCreate) -> StageConfigResponse:
    """Create a new custom stage. Built-in stage IDs cannot be reused."""
    if body.stage_id in BUILTIN_STAGE_IDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{body.stage_id}' is a built-in stage ID and cannot be recreated.",
        )

    existing = await crud.get_stage_config(body.stage_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stage '{body.stage_id}' already exists.",
        )

    stage = await crud.create_stage_config(body)
    return _to_response(stage, agent_count=0)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /admin/stage-configs/{stage_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{stage_id}",
    response_model=StageConfigResponse,
    summary="Update a stage config",
    description=(
        "Built-in stages can be updated (display_name, color, etc.) "
        "but their ``stage_id`` and ``is_builtin`` flag cannot be changed."
    ),
)
async def update_stage_config(
    stage_id: str, body: StageConfigUpdate
) -> StageConfigResponse:
    """Partially update a stage config."""
    stage = await crud.get_stage_config(stage_id)
    if stage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage '{stage_id}' not found.",
        )

    updated = await crud.update_stage_config(stage_id, body)
    count = await crud.count_agents_by_stage(stage_id)
    return _to_response(updated, agent_count=count)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /admin/stage-configs/{stage_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom stage",
    description=(
        "Built-in stages cannot be deleted. "
        "Agents in the deleted stage are reassigned to the 'custom' stage."
    ),
)
async def delete_stage_config(stage_id: str) -> None:
    """Delete a custom stage and reassign its agents to 'custom'."""
    stage = await crud.get_stage_config(stage_id)
    if stage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stage '{stage_id}' not found.",
        )

    if stage.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete built-in stage '{stage_id}'.",
        )

    # Reassign orphaned agents to the "custom" catch-all stage
    reassigned = await crud.reassign_agents_stage(stage_id, "custom")
    logger.info(
        "Reassigned %d agent(s) from deleted stage '%s' to 'custom'.",
        reassigned,
        stage_id,
    )

    await crud.delete_stage_config(stage_id)
