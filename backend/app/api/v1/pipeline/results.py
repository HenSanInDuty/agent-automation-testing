"""
pipeline/results.py – Result retrieval and report export endpoints.

Endpoints:
    GET /pipeline/runs/{run_id}/results             – all agent outputs
    GET /pipeline/runs/{run_id}/results/{node_id}   – single node output
    GET /pipeline/runs/{run_id}/export/html         – HTML report download
    GET /pipeline/runs/{run_id}/export/docx         – DOCX report download
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.db import crud
from app.schemas.pipeline import PipelineResultResponse

from ._helpers import _get_run_or_404, _result_to_response

logger = logging.getLogger(__name__)

router = APIRouter()

_PW_AGENTS = frozenset({"playwright_spec_writer", "playwright_fixture_writer"})


async def _ensure_playwright_artifacts(run_id: str, storage) -> None:  # type: ignore[type-arg]
    """When MinIO has no playwright files, synthesize them from DB node results.

    Delegates extraction to playwright_output_parser which handles all LLM formats.
    """
    from app.core.playwright_output_parser import extract_playwright_files

    loop = asyncio.get_running_loop()

    # Skip if MinIO already has files
    existing = await loop.run_in_executor(None, storage.list_playwright_files, run_id)
    if existing:
        return

    # Query all results and filter to playwright agent nodes
    db_results = await crud.get_pipeline_results(run_id)
    if not db_results:
        return

    for node_result in db_results:
        agent_id_val = node_result.agent_id or ""
        if agent_id_val not in _PW_AGENTS:
            continue

        output = node_result.output or {}
        files_map = extract_playwright_files(agent_id_val, output)
        for filename, content in files_map.items():
            await loop.run_in_executor(
                None, storage.upload_file_content,
                run_id, filename, content, "playwright", "text/plain",
            )
            logger.info(
                "[results] Uploaded synthesized artifact from DB: run=%s file=%s",
                run_id, filename,
            )


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


# ─────────────────────────────────────────────────────────────────────────────
# Playwright artifact file endpoints (MinIO-backed)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/artifacts/playwright",
    summary="List generated Playwright files",
    description="Returns a list of generated Playwright source files for a run.",
)
async def list_playwright_artifacts(run_id: str) -> list[dict]:
    """List all files stored in MinIO under runs/{run_id}/playwright/.

    If MinIO is empty and the run has playwright DB results, synthesizes
    TypeScript artifacts from the stored node outputs and uploads them first.
    """
    from app.services.storage_service import storage

    await _get_run_or_404(run_id)
    loop = asyncio.get_running_loop()
    files = await loop.run_in_executor(None, storage.list_playwright_files, run_id)
    if not files:
        await _ensure_playwright_artifacts(run_id, storage)
        files = await loop.run_in_executor(None, storage.list_playwright_files, run_id)
    return files


@router.get(
    "/runs/{run_id}/artifacts/playwright/zip",
    summary="Download all Playwright files as a ZIP archive",
    description="Bundles all generated Playwright source files into a single .zip download.",
    response_class=Response,
)
async def download_playwright_zip(run_id: str) -> Response:
    """Build a ZIP of all MinIO playwright artifacts and stream it."""
    from fastapi.responses import Response as FastAPIResponse
    from app.services.storage_service import storage

    await _get_run_or_404(run_id)
    loop = asyncio.get_running_loop()

    # Ensure artifacts exist (synthesize from DB if needed)
    await _ensure_playwright_artifacts(run_id, storage)

    zip_bytes = await loop.run_in_executor(None, storage.build_playwright_zip, run_id)

    if not zip_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Playwright artifacts found for this run.",
        )

    filename = f"playwright-tests-{run_id[:8]}.zip"
    return FastAPIResponse(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/runs/{run_id}/artifacts/playwright/file",
    summary="Download a single Playwright artifact file",
    description="Downloads a specific file from the Playwright artifacts directory.",
    response_class=Response,
)
async def download_playwright_file(
    run_id: str,
    path: Annotated[str, Query(description="Relative file path, e.g. tests/auth.spec.ts")],
) -> Response:
    """Download a single file from MinIO: runs/{run_id}/playwright/{path}."""
    import mimetypes
    import posixpath
    from fastapi.responses import Response as FastAPIResponse
    from app.services.storage_service import storage

    await _get_run_or_404(run_id)

    # Sanitise: reject any path traversal attempts
    normalised = posixpath.normpath(path)
    if normalised.startswith("..") or "//" in path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path.")

    loop = asyncio.get_running_loop()
    try:
        content = await loop.run_in_executor(
            None, storage.download_playwright_file, run_id, normalised
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {path}")

    filename = posixpath.basename(normalised)
    mime, _ = mimetypes.guess_type(filename)
    return FastAPIResponse(
        content=content,
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
