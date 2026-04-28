"""
pipeline/results.py – Result retrieval and report export endpoints.

Endpoints:
    GET /pipeline/runs/{run_id}/results             – all agent outputs
    GET /pipeline/runs/{run_id}/results/{node_id}   – single node output
    GET /pipeline/runs/{run_id}/export/html         – HTML report download
    GET /pipeline/runs/{run_id}/export/docx         – DOCX report download
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.db import crud
from app.schemas.pipeline import PipelineResultResponse

from ._helpers import _get_run_or_404, _result_to_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/runs/{run_id}/results",
    response_model=list[PipelineResultResponse],
    summary="Get all agent outputs for a pipeline run",
    description=(
        "Returns the persisted output of every agent for the given run, "
        "ordered by creation time. Optionally filter by ``stage`` or ``agent_id``."
    ),
)
async def get_pipeline_results(
    run_id: str,
    stage: Optional[str] = Query(
        default=None,
        description="Filter by stage: ingestion | testcase | execution | reporting",
    ),
    agent_id: Optional[str] = Query(
        default=None,
        description="Filter by agent slug, e.g. 'requirement_analyzer'",
    ),
) -> list[PipelineResultResponse]:
    """Retrieve all agent output documents for a run."""
    await _get_run_or_404(run_id)

    raw_results = await crud.get_pipeline_results(
        run_id, stage=stage, agent_id=agent_id
    )
    return [
        PipelineResultResponse(
            id=str(r.id),
            run_id=r.run_id,
            stage=r.stage or "",
            agent_id=r.agent_id or "",
            output=r.output,
            created_at=r.created_at,
        )
        for r in raw_results
    ]


@router.get(
    "/runs/{run_id}/results/{node_id}",
    response_model=PipelineResultResponse,
    summary="Get result for a specific node in a pipeline run",
    description=(
        "Returns the persisted output of a single DAG node for the given run."
    ),
)
async def get_node_result(run_id: str, node_id: str) -> PipelineResultResponse:
    """Retrieve the output of a specific node in a pipeline run."""
    result = await crud.get_pipeline_result_by_node(run_id, node_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No result found for node '{node_id}' in run '{run_id}'.",
        )
    return _result_to_response(result)


@router.get(
    "/runs/{run_id}/export/html",
    summary="Download pipeline report as HTML",
    description="Generates a self-contained HTML report for a completed pipeline run.",
    response_class=Response,
)
async def export_report_html(run_id: str) -> Response:
    """Download the pipeline report as a self-contained HTML file."""
    from fastapi.responses import Response as FastAPIResponse

    from app.services.export_service import ExportService

    await _get_run_or_404(run_id)
    try:
        service = ExportService(run_id)
        html_bytes = await service.export_html()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    filename = f"auto-at-report-{run_id[:8]}.html"
    return FastAPIResponse(
        content=html_bytes,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/runs/{run_id}/export/docx",
    summary="Download pipeline report as DOCX",
    description="Generates a Microsoft Word DOCX report for a completed pipeline run.",
    response_class=Response,
)
async def export_report_docx(run_id: str) -> Response:
    """Download the pipeline report as a DOCX (Microsoft Word) file."""
    from fastapi.responses import Response as FastAPIResponse

    from app.services.export_service import ExportService

    await _get_run_or_404(run_id)
    try:
        service = ExportService(run_id)
        docx_bytes = await service.export_docx()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    filename = f"auto-at-report-{run_id[:8]}.docx"
    return FastAPIResponse(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
