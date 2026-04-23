from __future__ import annotations

"""
pipeline_templates/crud.py – CRUD endpoints for pipeline templates.

Endpoints:
    GET    /pipeline-templates                    – list all templates
    POST   /pipeline-templates                    – create new template
    GET    /pipeline-templates/{template_id}      – get full template
    PUT    /pipeline-templates/{template_id}      – update template
    DELETE /pipeline-templates/{template_id}      – hard delete (no runs)
    POST   /pipeline-templates/{template_id}/archive – soft delete
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.db import crud
from app.schemas.pipeline_template import (
    PipelineTemplateCreate,
    PipelineTemplateListItem,
    PipelineTemplateResponse,
    PipelineTemplateUpdate,
)

from ._helpers import (
    PaginatedTemplateResponse,
    _get_or_404,
    _to_response,
    _validate_dag_or_422,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedTemplateResponse,
    summary="List all pipeline templates",
    description=(
        "Return all pipeline templates sorted by ``updated_at`` descending. "
        "Pass ``include_archived=true`` to include soft-deleted templates. "
        "Pass ``tag=<value>`` to filter by a specific tag (exact match). "
        "Results are paginated via ``page`` and ``page_size``."
    ),
)
async def list_templates(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    include_archived: bool = Query(
        False,
        description="When true, archived templates are included in the response.",
    ),
    tag: Optional[str] = Query(
        None,
        description="Filter results to templates that carry this exact tag.",
    ),
) -> PaginatedTemplateResponse:
    """List all pipeline templates with lightweight metadata."""
    templates = await crud.get_all_pipeline_templates(
        include_archived=include_archived, tag=tag
    )

    items: list[PipelineTemplateListItem] = []
    for tmpl in templates:
        last_run = await crud.get_latest_run_for_template(tmpl.template_id)
        items.append(
            PipelineTemplateListItem(
                id=str(tmpl.id),
                template_id=tmpl.template_id,
                name=tmpl.name,
                description=tmpl.description,
                version=tmpl.version,
                is_builtin=tmpl.is_builtin,
                is_archived=tmpl.is_archived,
                tags=tmpl.tags,
                node_count=len(tmpl.nodes),
                edge_count=len(tmpl.edges),
                last_run_at=last_run.created_at if last_run else None,
                last_run_status=last_run.status if last_run else None,
                created_at=tmpl.created_at,
                updated_at=tmpl.updated_at,
            )
        )

    total = len(items)
    start = (page - 1) * page_size
    paginated_items = items[start : start + page_size]

    return PaginatedTemplateResponse(
        items=paginated_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=PipelineTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new pipeline template",
    description=(
        "Create a new pipeline template.  If ``nodes`` is non-empty the DAG "
        "is validated before persisting; a blank template (no nodes) is "
        "accepted without DAG validation."
    ),
)
async def create_template(
    body: PipelineTemplateCreate,
) -> PipelineTemplateResponse:
    """Create a new pipeline template."""
    existing = await crud.get_pipeline_template(body.template_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A pipeline template with template_id='{body.template_id}' already exists.",
        )

    if body.nodes:
        _validate_dag_or_422(body.nodes, body.edges)

    doc = await crud.create_pipeline_template(body.model_dump())
    logger.info("Created pipeline template: %s", doc.template_id)
    return _to_response(doc)


@router.get(
    "/{template_id}",
    response_model=PipelineTemplateResponse,
    summary="Get a pipeline template by ID",
    description="Return the full pipeline template document, including all nodes and edges.",
)
async def get_template(template_id: str) -> PipelineTemplateResponse:
    """Retrieve a single pipeline template by its slug."""
    doc = await _get_or_404(template_id)
    return _to_response(doc)


@router.put(
    "/{template_id}",
    response_model=PipelineTemplateResponse,
    summary="Update a pipeline template",
    description=(
        "Partially update a pipeline template.  Only fields present in the "
        "request body are modified.  If ``nodes`` or ``edges`` are provided, "
        "the entire DAG is replaced and re-validated.  The document ``version`` "
        "is auto-incremented on every successful update."
    ),
)
async def update_template(
    template_id: str,
    body: PipelineTemplateUpdate,
) -> PipelineTemplateResponse:
    """Update a pipeline template with partial data."""
    await _get_or_404(template_id)

    if body.nodes is not None and len(body.nodes) > 0:
        edges = body.edges if body.edges is not None else []
        _validate_dag_or_422(body.nodes, edges)

    update_data = body.model_dump(exclude_none=True)

    if not update_data:
        doc = await crud.get_pipeline_template(template_id)
        return _to_response(doc)  # type: ignore[arg-type]

    updated = await crud.update_pipeline_template(template_id, update_data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline template '{template_id}' not found.",
        )

    logger.info("Updated pipeline template: %s (v%d)", template_id, updated.version)
    return _to_response(updated)


@router.delete(
    "/{template_id}",
    summary="Hard-delete a pipeline template",
    description=(
        "Permanently remove a pipeline template from the database.  "
        "Built-in templates cannot be deleted (HTTP 403); archive them instead.  "
        "Templates with one or more associated pipeline runs cannot be deleted "
        "(HTTP 409); archive them instead."
    ),
)
async def delete_template(template_id: str) -> dict:  # type: ignore[type-arg]
    """Permanently delete a pipeline template."""
    doc = await _get_or_404(template_id)

    if doc.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Pipeline template '{template_id}' is a built-in template and "
                "cannot be deleted.  Archive it instead."
            ),
        )

    run_count = await crud.count_runs_for_template(template_id)
    if run_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Pipeline template '{template_id}' has {run_count} associated "
                "run(s) and cannot be hard-deleted.  Archive it instead."
            ),
        )

    deleted = await crud.delete_pipeline_template(template_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline template '{template_id}' not found.",
        )

    logger.info("Deleted pipeline template: %s", template_id)
    return {"deleted": True, "template_id": template_id}


@router.post(
    "/{template_id}/archive",
    response_model=PipelineTemplateResponse,
    summary="Archive (soft-delete) a pipeline template",
    description=(
        "Mark a pipeline template as archived.  Archived templates are hidden "
        "from the default list view but remain in the database and can be "
        "restored by updating ``is_archived`` to ``false`` via the PUT endpoint."
    ),
)
async def archive_template(template_id: str) -> PipelineTemplateResponse:
    """Soft-delete a pipeline template by setting ``is_archived = True``."""
    doc = await _get_or_404(template_id)

    if doc.is_archived:
        logger.debug("Template '%s' is already archived.", template_id)
        return _to_response(doc)

    updated = await crud.update_pipeline_template(template_id, {"is_archived": True})
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline template '{template_id}' not found.",
        )

    logger.info("Archived pipeline template: %s", template_id)
    return _to_response(updated)
