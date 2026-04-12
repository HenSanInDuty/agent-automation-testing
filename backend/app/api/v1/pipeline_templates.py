from __future__ import annotations

"""
api/v1/pipeline_templates.py – REST endpoints for Pipeline Template management.

All route handlers are ``async`` and delegate all DB operations to
``app.db.crud``.  Pipeline template IDs are unique URL-safe slugs
(e.g. ``"auto-testing-pipeline"``); MongoDB ObjectIds are returned as
plain strings in every response.

Endpoints:
    GET    /pipeline-templates                            – list all templates
    POST   /pipeline-templates                            – create new template
    POST   /pipeline-templates/import                     – import from JSON export
    GET    /pipeline-templates/{template_id}/export       – export as JSON
    POST   /pipeline-templates/{template_id}/validate     – validate DAG
    POST   /pipeline-templates/{template_id}/archive      – soft delete
    POST   /pipeline-templates/{template_id}/clone        – clone to new template
    GET    /pipeline-templates/{template_id}              – get full template
    PUT    /pipeline-templates/{template_id}              – update template
    DELETE /pipeline-templates/{template_id}              – hard delete (no runs)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import Field as PydanticField

from app.core.dag_resolver import DAGResolver, DAGValidationError
from app.db import crud
from app.db.models import PipelineEdgeConfig, PipelineNodeConfig
from app.schemas.pipeline_template import (
    DAGValidationResponse,
    PipelineEdgeInput,
    PipelineNodeInput,
    PipelineTemplateCreate,
    PipelineTemplateListItem,
    PipelineTemplateResponse,
    PipelineTemplateUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline-templates", tags=["Pipeline Templates"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / response models local to this router
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
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


def _to_response(template) -> PipelineTemplateResponse:  # type: ignore[return]
    """Convert a ``PipelineTemplateDocument`` to a ``PipelineTemplateResponse``.

    Uses ``model_dump(mode="json")`` on every node so that the ``NodeType``
    str-enum is serialised to its plain string value (e.g. ``"agent"``) before
    being passed to ``PipelineNodeInput``.  Without ``mode="json"`` the
    enum value itself may be returned, causing a Pydantic validation error
    because ``PipelineNodeInput.node_type`` is declared as a plain ``str``.

    Args:
        template: A :class:`~app.db.models.PipelineTemplateDocument` instance.

    Returns:
        A fully-populated
        :class:`~app.schemas.pipeline_template.PipelineTemplateResponse`.
    """
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
    """Fetch a pipeline template by slug, or raise HTTP 404.

    Args:
        template_id: URL-safe slug identifier (e.g. ``"auto-testing"``).

    Returns:
        The matching :class:`~app.db.models.PipelineTemplateDocument`.

    Raises:
        HTTPException: 404 if no document exists for *template_id*.
    """
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
    """Validate a DAG described by input schemas and raise HTTP 422 on failure.

    Converts :class:`~app.schemas.pipeline_template.PipelineNodeInput` /
    :class:`~app.schemas.pipeline_template.PipelineEdgeInput` objects into
    their ``app.db.models`` equivalents and runs
    :meth:`~app.core.dag_resolver.DAGResolver.validate`.

    This helper should only be called when at least one node is present
    (an empty node list is allowed for blank draft templates and skips
    validation entirely).

    Args:
        nodes: List of node input schemas to validate.
        edges: List of edge input schemas to validate.

    Raises:
        HTTPException: 422 with a descriptive ``detail`` message if the DAG
            is structurally invalid (cycle, missing INPUT/OUTPUT, orphan, etc.).
    """
    db_nodes = [PipelineNodeConfig(**n.model_dump()) for n in nodes]
    db_edges = [PipelineEdgeConfig(**e.model_dump()) for e in edges]
    try:
        DAGResolver(db_nodes, db_edges).validate()
    except DAGValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"DAG validation failed: {exc}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline-templates  – list
# ─────────────────────────────────────────────────────────────────────────────


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
    """List all pipeline templates with lightweight metadata.

    Each item includes the last-run timestamp and status fetched from
    the most recent ``PipelineRunDocument`` associated with the template.

    Args:
        include_archived: Include soft-deleted templates when ``True``.
        tag: Optional exact-match tag filter.

    Returns:
        A list of :class:`~app.schemas.pipeline_template.PipelineTemplateListItem`
        sorted by ``updated_at`` descending.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline-templates  – create
# ─────────────────────────────────────────────────────────────────────────────


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
    """Create a new pipeline template.

    Validates uniqueness of ``template_id`` and, when at least one node is
    provided, runs a full DAG structural validation before inserting the
    document.

    Args:
        body: Validated request payload
            (:class:`~app.schemas.pipeline_template.PipelineTemplateCreate`).

    Returns:
        The newly-created template as a
        :class:`~app.schemas.pipeline_template.PipelineTemplateResponse`.

    Raises:
        HTTPException: 409 if ``template_id`` is already taken.
        HTTPException: 422 if the DAG structure is invalid.
    """
    # Uniqueness check
    existing = await crud.get_pipeline_template(body.template_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A pipeline template with template_id='{body.template_id}' already exists.",
        )

    # DAG validation (only when nodes are present)
    if body.nodes:
        _validate_dag_or_422(body.nodes, body.edges)

    doc = await crud.create_pipeline_template(body.model_dump())
    logger.info("Created pipeline template: %s", doc.template_id)
    return _to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline-templates/import  – import from JSON
# NOTE: Must be declared BEFORE /{template_id} routes so the static path
#       "/import" is not captured by the path parameter.
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/import",
    response_model=PipelineTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a pipeline template from a JSON export",
    description=(
        "Accept a JSON object previously produced by the ``GET "
        "/pipeline-templates/{template_id}/export`` endpoint.  The "
        "``export_type`` field must equal ``'pipeline_template'``.  "
        "If the ``template_id`` embedded in the export already exists in the "
        "database, a numeric suffix (``-1``, ``-2``, …) is appended until a "
        "unique slug is found."
    ),
)
async def import_template(
    body: dict = Body(..., description="JSON object produced by the export endpoint."),  # type: ignore[assignment]
) -> PipelineTemplateResponse:
    """Import a pipeline template from a previously-exported JSON document.

    Validates the ``export_type`` discriminator field, extracts the embedded
    ``template`` payload, and creates a new document — resolving any
    ``template_id`` collisions automatically by appending a numeric suffix.

    Args:
        body: Raw JSON dict.  Must contain ``export_type`` and ``template`` keys.

    Returns:
        The newly-created template as a
        :class:`~app.schemas.pipeline_template.PipelineTemplateResponse`.

    Raises:
        HTTPException: 422 if ``export_type`` is missing or incorrect.
        HTTPException: 422 if the embedded template data fails schema validation.
    """
    if body.get("export_type") != "pipeline_template":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid import payload: 'export_type' must be 'pipeline_template'. "
                f"Got: {body.get('export_type')!r}"
            ),
        )

    template_data: dict = body.get("template", {})  # type: ignore[assignment]

    # Validate schema
    try:
        create_input = PipelineTemplateCreate(**template_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template data failed schema validation: {exc}",
        )

    # Resolve template_id conflicts
    base_id = create_input.template_id
    candidate_id = base_id
    suffix = 1
    while await crud.get_pipeline_template(candidate_id) is not None:
        candidate_id = f"{base_id}-{suffix}"
        suffix += 1

    if candidate_id != base_id:
        logger.info(
            "Import: template_id '%s' already exists — using '%s' instead.",
            base_id,
            candidate_id,
        )
        create_input = create_input.model_copy(update={"template_id": candidate_id})

    # DAG validation (only when nodes are present)
    if create_input.nodes:
        _validate_dag_or_422(create_input.nodes, create_input.edges)

    doc = await crud.create_pipeline_template(create_input.model_dump())
    logger.info("Imported pipeline template as: %s", doc.template_id)
    return _to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline-templates/{template_id}/export
# NOTE: Sub-path routes declared before /{template_id} for route safety.
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{template_id}/export",
    summary="Export a pipeline template as a JSON file",
    description=(
        "Return the full pipeline template serialised as a downloadable JSON "
        "file.  The response includes a ``Content-Disposition: attachment`` "
        "header so browsers will prompt a file-save dialog."
    ),
)
async def export_template(template_id: str) -> JSONResponse:
    """Export a pipeline template as a self-contained JSON document.

    The export envelope includes a version discriminator and an
    ``export_type`` field so that :func:`import_template` can validate the
    payload on re-import.

    Args:
        template_id: URL-safe slug of the template to export.

    Returns:
        A :class:`~fastapi.responses.JSONResponse` with
        ``Content-Disposition: attachment; filename="<template_id>.json"``.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    doc = await _get_or_404(template_id)

    template_dict = {
        "template_id": doc.template_id,
        "name": doc.name,
        "description": doc.description,
        "version": doc.version,
        "nodes": [n.model_dump(mode="json") for n in doc.nodes],
        "edges": [e.model_dump(mode="json") for e in doc.edges],
        "tags": doc.tags,
        "is_builtin": doc.is_builtin,
        "is_archived": doc.is_archived,
        "node_count": len(doc.nodes),
        "edge_count": len(doc.edges),
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }

    payload = {
        "auto_at_version": "3.0",
        "export_type": "pipeline_template",
        "template": template_dict,
    }

    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{template_id}.json"',
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline-templates/{template_id}/validate
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{template_id}/validate",
    response_model=DAGValidationResponse,
    summary="Validate the DAG of a pipeline template",
    description=(
        "Run a full structural validation of the template's DAG and compute "
        "parallel execution layers.  Returns ``is_valid=true`` together with "
        "layering information on success, or ``is_valid=false`` with a list "
        "of error messages on failure.  This endpoint always returns HTTP 200 "
        "— the ``is_valid`` flag in the body communicates the validation result."
    ),
)
async def validate_template(template_id: str) -> DAGValidationResponse:
    """Validate the DAG structure of a stored pipeline template.

    Retrieves the template from the database and runs
    :meth:`~app.core.dag_resolver.DAGResolver.get_execution_layers` to
    perform a full validation and compute the parallel execution schedule.

    Args:
        template_id: URL-safe slug of the template to validate.

    Returns:
        A :class:`~app.schemas.pipeline_template.DAGValidationResponse`
        describing whether the DAG is valid and, if so, the computed
        execution layers.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    doc = await _get_or_404(template_id)

    try:
        resolver = DAGResolver(doc.nodes, doc.edges)
        layers = resolver.get_execution_layers()

        total_layers = len(layers)
        total_nodes = sum(len(layer) for layer in layers)
        speedup: Optional[float] = (
            round(total_nodes / total_layers, 2) if total_layers > 0 else None
        )

        return DAGValidationResponse(
            is_valid=True,
            errors=[],
            warnings=[],
            execution_layers=layers,
            total_layers=total_layers,
            total_nodes=total_nodes,
            estimated_parallel_speedup=speedup,
        )

    except DAGValidationError as exc:
        # The error message is all individual failures joined by "; "
        error_list = [e.strip() for e in str(exc).split(";") if e.strip()]
        return DAGValidationResponse(
            is_valid=False,
            errors=error_list,
            warnings=[],
            execution_layers=[],
            total_layers=0,
            total_nodes=0,
            estimated_parallel_speedup=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline-templates/{template_id}/archive
# ─────────────────────────────────────────────────────────────────────────────


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
    """Soft-delete a pipeline template by setting ``is_archived = True``.

    Archived templates are excluded from the default list endpoint unless
    ``include_archived=true`` is passed.  The document is not deleted from
    the database, preserving historical run associations.

    Args:
        template_id: URL-safe slug of the template to archive.

    Returns:
        The updated template as a
        :class:`~app.schemas.pipeline_template.PipelineTemplateResponse`.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    doc = await _get_or_404(template_id)

    if doc.is_archived:
        # Idempotent — return current state without an extra write
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


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline-templates/{template_id}/clone
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{template_id}/clone",
    response_model=PipelineTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Clone a pipeline template",
    description=(
        "Create a new pipeline template that is an exact copy of the source "
        "template.  The clone starts at version 1, is not built-in, and is "
        "not archived.  Body params: new_template_id, new_name."
    ),
)
async def clone_template(
    template_id: str,
    body: CloneTemplateRequest,
) -> PipelineTemplateResponse:
    """Clone an existing pipeline template into a new document.

    The cloned template is an independent copy: changes to the clone do not
    affect the original, and vice versa.

    Args:
        template_id: URL-safe slug of the source template.
        new_template_id: Unique slug for the new cloned template.
        new_name: Display name for the new cloned template.

    Returns:
        The newly-created cloned template as a
        :class:`~app.schemas.pipeline_template.PipelineTemplateResponse`.

    Raises:
        HTTPException: 404 if the source template does not exist.
        HTTPException: 409 if ``new_template_id`` is already taken.
    """
    source = await _get_or_404(template_id)

    # Ensure the target slug is available
    existing = await crud.get_pipeline_template(body.new_template_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot clone: a template with template_id='{body.new_template_id}' "
                "already exists."
            ),
        )

    cloned = await crud.clone_pipeline_template(
        source, body.new_template_id, body.new_name
    )
    logger.info("Cloned template '%s' → '%s'", template_id, body.new_template_id)
    return _to_response(cloned)


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /pipeline-templates/{template_id}/node-stage  – set/clear node stage
# ─────────────────────────────────────────────────────────────────────────────


@router.patch(
    "/{template_id}/node-stage",
    status_code=status.HTTP_200_OK,
    summary="Set or clear the stage on a single DAG node",
)
async def update_node_stage(
    template_id: str,
    body: NodeStageUpdate,
    response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    result = await crud.update_node_stage(template_id, body.node_id, body.stage_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' or node '{body.node_id}' not found.",
        )
    return {
        "ok": True,
        "template_id": template_id,
        "node_id": body.node_id,
        "stage_id": body.stage_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline-templates/{template_id}  – get one
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{template_id}",
    response_model=PipelineTemplateResponse,
    summary="Get a pipeline template by ID",
    description="Return the full pipeline template document, including all nodes and edges.",
)
async def get_template(template_id: str) -> PipelineTemplateResponse:
    """Retrieve a single pipeline template by its slug.

    Args:
        template_id: URL-safe slug of the template to fetch.

    Returns:
        The matching template as a
        :class:`~app.schemas.pipeline_template.PipelineTemplateResponse`.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    doc = await _get_or_404(template_id)
    return _to_response(doc)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /pipeline-templates/{template_id}  – update
# ─────────────────────────────────────────────────────────────────────────────


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
    """Update a pipeline template with partial data.

    All fields in :class:`~app.schemas.pipeline_template.PipelineTemplateUpdate`
    are optional.  Only non-``None`` fields are written to the document.
    When ``nodes`` is provided and non-empty, a DAG validation pass runs
    before the update is persisted.

    Args:
        template_id: URL-safe slug of the template to update.
        body: Partial update payload.

    Returns:
        The updated template as a
        :class:`~app.schemas.pipeline_template.PipelineTemplateResponse`.

    Raises:
        HTTPException: 404 if the template does not exist.
        HTTPException: 422 if the updated DAG structure is invalid.
    """
    # Ensure the template exists before running validation
    await _get_or_404(template_id)

    # DAG validation when nodes are being replaced
    if body.nodes is not None and len(body.nodes) > 0:
        edges = body.edges if body.edges is not None else []
        _validate_dag_or_422(body.nodes, edges)

    # Build update dict from only the fields that were explicitly provided
    update_data = body.model_dump(exclude_none=True)

    if not update_data:
        # Nothing to update — return current state
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


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /pipeline-templates/{template_id}  – hard delete
# ─────────────────────────────────────────────────────────────────────────────


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
    """Permanently delete a pipeline template.

    Two guards are enforced before deletion:

    1. **Built-in guard** — built-in templates (``is_builtin=True``) may not be
       hard-deleted.  Use the archive endpoint instead.
    2. **Run guard** — templates that have associated pipeline run documents
       may not be hard-deleted to preserve audit history.  Archive them instead.

    Args:
        template_id: URL-safe slug of the template to delete.

    Returns:
        A confirmation dict with ``deleted=True`` and the ``template_id``.

    Raises:
        HTTPException: 404 if the template does not exist.
        HTTPException: 403 if the template is a built-in template.
        HTTPException: 409 if the template has associated pipeline runs.
    """
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
