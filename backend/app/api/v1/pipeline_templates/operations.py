"""
pipeline_templates/operations.py – Import/export/validate/clone and node operations.

Endpoints:
    POST   /pipeline-templates/import                    – import from JSON export
    GET    /pipeline-templates/{template_id}/export      – export as JSON
    POST   /pipeline-templates/{template_id}/validate    – validate DAG
    POST   /pipeline-templates/{template_id}/clone       – clone to new template
    PATCH  /pipeline-templates/{template_id}/node-stage  – set/clear node stage
    POST   /pipeline-templates/{template_id}/nodes       – append a node
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Response, status
from fastapi.responses import JSONResponse

from app.core.dag_resolver import DAGResolver, DAGValidationError
from app.db import crud
from app.schemas.pipeline_template import (
    DAGValidationResponse,
    PipelineNodeInput,
    PipelineTemplateCreate,
    PipelineTemplateResponse,
)

from ._helpers import (
    CloneTemplateRequest,
    NodeStageUpdate,
    _get_or_404,
    _to_response,
    _validate_dag_or_422,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# NOTE: /import must be declared BEFORE /{template_id} routes so the static
# path "/import" is not captured by the path parameter.
@router.post(
    "/import",
    response_model=PipelineTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a pipeline template from a JSON export",
    description=(
        "Accept a JSON object previously produced by the ``GET "
        "/pipeline-templates/{template_id}/export`` endpoint.  The "
        "``export_type`` field must equal ``'pipeline_template'``."
    ),
)
async def import_template(
    body: dict = Body(..., description="JSON object produced by the export endpoint."),  # type: ignore[assignment]
) -> PipelineTemplateResponse:
    """Import a pipeline template from a previously-exported JSON document."""
    if body.get("export_type") != "pipeline_template":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid import payload: 'export_type' must be 'pipeline_template'. "
                f"Got: {body.get('export_type')!r}"
            ),
        )

    template_data: dict = body.get("template", {})  # type: ignore[assignment]

    try:
        create_input = PipelineTemplateCreate(**template_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template data failed schema validation: {exc}",
        ) from exc

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

    if create_input.nodes:
        _validate_dag_or_422(create_input.nodes, create_input.edges)

    doc = await crud.create_pipeline_template(create_input.model_dump())
    logger.info("Imported pipeline template as: %s", doc.template_id)
    return _to_response(doc)


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
    """Export a pipeline template as a self-contained JSON document."""
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


@router.post(
    "/{template_id}/validate",
    response_model=DAGValidationResponse,
    summary="Validate the DAG of a pipeline template",
    description=(
        "Run a full structural validation of the template's DAG and compute "
        "parallel execution layers.  Returns ``is_valid=true`` on success or "
        "``is_valid=false`` with error messages on failure.  Always returns HTTP 200."
    ),
)
async def validate_template(template_id: str) -> DAGValidationResponse:
    """Validate the DAG structure of a stored pipeline template."""
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
    """Clone an existing pipeline template into a new document."""
    source = await _get_or_404(template_id)

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
    """Set or clear the stage label on a DAG node."""
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


@router.post(
    "/{template_id}/nodes",
    response_model=PipelineTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a node to a pipeline template",
    description=(
        "Adds a single node to the template's node list without running "
        "full DAG validation.  Use this when creating an agent from the Admin "
        "UI so the node appears in the pipeline immediately."
    ),
)
async def append_node_to_template(
    template_id: str,
    body: PipelineNodeInput,
    response: Response,
) -> PipelineTemplateResponse:
    """Append one node to the pipeline template."""
    await _get_or_404(template_id)
    response.headers["Cache-Control"] = "no-store"

    try:
        updated = await crud.append_pipeline_node(template_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline template '{template_id}' not found.",
        )

    logger.info("Appended node '%s' to template '%s'", body.node_id, template_id)
    return _to_response(updated)
