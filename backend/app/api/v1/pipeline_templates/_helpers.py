"""
pipeline_templates/_helpers.py – Shared helpers, models, and validators
for pipeline template API endpoints.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel
from pydantic import Field as PydanticField

from app.core.dag_resolver import DAGResolver, DAGValidationError
from app.db import crud
from app.db.models import PipelineEdgeConfig, PipelineNodeConfig
from app.schemas.pipeline_template import (
    PipelineEdgeInput,
    PipelineNodeInput,
    PipelineTemplateListItem,
    PipelineTemplateResponse,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Request / response models
# ─────────────────────────────────────────────────────────────────────────────


class CloneTemplateRequest(BaseModel):
    """Request body for cloning a pipeline template."""

    new_template_id: str = PydanticField(
        ...,
        pattern=r"^[a-z][a-z0-9_-]{2,49}$",
        description="URL-safe slug for the cloned template.",
    )
    new_name: str = PydanticField(
        ...,
        min_length=2,
        max_length=200,
        description="Display name for the cloned template.",
    )


class PaginatedTemplateResponse(BaseModel):
    """Paginated response for pipeline template list endpoint."""

    items: list[PipelineTemplateListItem]
    total: int
    page: int
    page_size: int


class NodeStageUpdate(BaseModel):
    """Assign or clear a stage on a single DAG node."""

    node_id: str
    stage_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────


def _to_response(template) -> PipelineTemplateResponse:  # type: ignore[return]
    """Convert a PipelineTemplateDocument to a PipelineTemplateResponse."""
    nodes = [PipelineNodeInput(**n.model_dump(mode="json")) for n in template.nodes]
    edges = [PipelineEdgeInput(**e.model_dump(mode="json")) for e in template.edges]

    return PipelineTemplateResponse(
        id=str(template.id),
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        version=template.version,
        nodes=nodes,
        edges=edges,
        is_builtin=template.is_builtin,
        is_archived=template.is_archived,
        tags=template.tags,
        node_count=len(template.nodes),
        edge_count=len(template.edges),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


async def _get_or_404(template_id: str):  # type: ignore[return]
    """Fetch a pipeline template by slug, or raise HTTP 404."""
    doc = await crud.get_pipeline_template(template_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline template '{template_id}' not found.",
        )
    return doc


def _validate_dag_or_422(
    nodes: list[PipelineNodeInput],
    edges: list[PipelineEdgeInput],
) -> None:
    """Validate a DAG described by input schemas and raise HTTP 422 on failure."""
    db_nodes = [PipelineNodeConfig(**n.model_dump()) for n in nodes]
    db_edges = [PipelineEdgeConfig(**e.model_dump()) for e in edges]
    try:
        DAGResolver(db_nodes, db_edges).validate()
    except DAGValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"DAG validation failed: {exc}",
        ) from exc
