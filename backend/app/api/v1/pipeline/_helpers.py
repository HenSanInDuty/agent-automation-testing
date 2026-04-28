"""
pipeline/_helpers.py – Shared helpers, constants, and response converters
for pipeline run API endpoints.
"""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel as _BaseModel

from app.config import settings
from app.db import crud
from app.db.models import PipelineRunDocument
from app.schemas.pipeline import (
    AGENT_STATUS_TO_FRONTEND,
    AgentRunResult,
    PipelineResultResponse,
    PipelineRunResponse,
    PipelineStatus,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────


class PipelineActionResponse(_BaseModel):
    """Response schema for pipeline action endpoints (pause/resume/cancel)."""

    status: str
    run_id: str
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Upload constants
# ─────────────────────────────────────────────────────────────────────────────

_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".doc",
    ".html",
    ".htm",
    ".rst",
    ".csv",
}
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/csv",
    "text/x-rst",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",  # generic fallback some browsers send
}

# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_run_or_404(run_id: str) -> PipelineRunDocument:
    """Fetch a pipeline run document or raise HTTP 404.

    Args:
        run_id: UUID string stored in ``PipelineRunDocument.run_id``.

    Returns:
        The matching :class:`~app.db.models.PipelineRunDocument`.

    Raises:
        HTTPException: 404 if no document exists for *run_id*.
    """
    doc = await crud.get_pipeline_run(run_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )
    return doc


# ─────────────────────────────────────────────────────────────────────────────
# Response converters
# ─────────────────────────────────────────────────────────────────────────────


async def _run_to_response(run: PipelineRunDocument) -> PipelineRunResponse:
    """Convert a PipelineRunDocument to the V2 API response schema."""
    raw_statuses: dict[str, str] = run.agent_statuses

    agent_runs: list[AgentRunResult] = []

    if raw_statuses:
        all_configs = await crud.get_all_agent_configs()
        config_map = {c.agent_id: c for c in all_configs}

        all_results = await crud.get_pipeline_results(run.run_id)
        results_map: dict[str, str] = {}
        for r in all_results:
            preview = (
                _json.dumps(r.output, ensure_ascii=False, default=str)[:15_000]
                if r.output is not None
                else None
            )
            results_map[r.agent_id or ""] = preview or ""

        for agent_id, raw_status in raw_statuses.items():
            config = config_map.get(agent_id)
            frontend_status = AGENT_STATUS_TO_FRONTEND.get(raw_status, "pending")
            agent_runs.append(
                AgentRunResult(
                    agent_id=agent_id,
                    display_name=config.display_name if config else agent_id,
                    stage=config.stage if config else "ingestion",
                    status=frontend_status,
                    output_preview=results_map.get(agent_id),
                    error_message=None,
                    started_at=None,
                    completed_at=None,
                )
            )

    return PipelineRunResponse(
        id=run.run_id,
        run_id=run.run_id,
        document_filename=run.document_name,
        status=PipelineStatus(run.status),
        llm_profile_id=run.llm_profile_id,
        current_stage=run.current_stage,
        completed_stages=run.completed_stages,
        agent_runs=agent_runs,
        error_message=run.error,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.finished_at,
    )


_SPECIAL_AGENT_IDS = frozenset({"__input__", "__output__"})


async def _dag_run_to_response(run: PipelineRunDocument) -> PipelineRunResponse:
    """Convert a V3 PipelineRunDocument to PipelineRunResponse."""
    node_results = await crud.get_pipeline_results(run.run_id)
    all_configs = await crud.get_all_agent_configs()
    config_map = {c.agent_id: c for c in all_configs}

    agent_runs: list[AgentRunResult] = []
    for r in node_results:
        aid = r.agent_id or ""
        if not aid or aid in _SPECIAL_AGENT_IDS:
            continue
        config = config_map.get(aid)
        agent_runs.append(
            AgentRunResult(
                agent_id=aid,
                display_name=config.display_name if config else aid,
                stage=config.stage if config else (r.stage or "agent"),
                status=r.status,
                output_preview=(
                    _json.dumps(r.output, ensure_ascii=False, default=str)[:15_000]
                    if r.output is not None
                    else None
                ),
                error_message=r.error_message,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
        )

    return PipelineRunResponse(
        id=run.run_id,
        run_id=run.run_id,
        status=PipelineStatus(run.status),
        template_id=run.template_id,
        llm_profile_id=run.llm_profile_id,
        document_filename=run.document_name,
        current_node=run.current_node,
        completed_nodes=run.completed_nodes,
        failed_nodes=run.failed_nodes,
        node_statuses=run.node_statuses,
        execution_layers=run.execution_layers,
        duration_seconds=run.duration_seconds,
        current_stage=run.current_stage,
        completed_stages=run.completed_stages,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        paused_at=run.paused_at,
        resumed_at=run.resumed_at,
        error_message=run.error_message or run.error,
        agent_runs=agent_runs,
    )


def _result_to_response(r: Any) -> PipelineResultResponse:
    """Convert a PipelineResultDocument to PipelineResultResponse."""
    return PipelineResultResponse(
        id=str(r.id),
        run_id=r.run_id,
        stage=r.stage or "",
        agent_id=r.agent_id or "",
        output=r.output,
        created_at=r.created_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Upload helpers
# ─────────────────────────────────────────────────────────────────────────────


def _validate_upload(file: UploadFile) -> None:
    """Raise HTTP 422/415 if the uploaded file fails basic validation."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file has no filename.",
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File extension '{suffix}' is not supported. "
                f"Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
            ),
        )


def _save_upload(file: UploadFile, run_id: str) -> tuple[str, str]:
    """Persist the uploaded file to ``UPLOAD_DIR/<run_id>/<original_filename>``.

    Returns:
        ``(document_name, absolute_file_path)``

    Raises:
        HTTPException: 413 if the file exceeds ``MAX_FILE_SIZE_MB``.
        HTTPException: 500 if an I/O error occurs while writing.
    """
    dest_dir = Path(settings.UPLOAD_DIR) / run_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    document_name = Path(file.filename or "upload").name
    dest_path = dest_dir / document_name
    max_bytes = settings.max_file_size_bytes
    bytes_written = 0

    try:
        with dest_path.open("wb") as out_file:
            while True:
                chunk = file.file.read(64 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    out_file.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"File exceeds the maximum allowed size of "
                            f"{settings.MAX_FILE_SIZE_MB} MB."
                        ),
                    )
                out_file.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {exc}",
        ) from exc

    logger.info(
        "[Pipeline] Saved upload run_id=%r  file=%r  bytes=%d",
        run_id,
        document_name,
        bytes_written,
    )
    return document_name, str(dest_path)
