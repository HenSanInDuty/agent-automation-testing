from __future__ import annotations

"""
api/v1/pipeline.py – REST endpoints for pipeline run management.

All route handlers are ``async`` and call Beanie CRUD functions directly —
no SQLAlchemy session is needed.  Pipeline run IDs are UUID strings stored
in the ``run_id`` field of :class:`~app.db.models.PipelineRunDocument`.

Endpoints:
    POST   /pipeline/run                          – upload document + start run
    GET    /pipeline/runs                         – paginated list of runs
    GET    /pipeline/runs/{run_id}                – get one run (with results)
    DELETE /pipeline/runs/{run_id}                – delete run + files
    POST   /pipeline/runs/{run_id}/pause          – pause a running pipeline
    POST   /pipeline/runs/{run_id}/resume         – resume a paused pipeline
    POST   /pipeline/runs/{run_id}/cancel         – request cancellation
    GET    /pipeline/runs/{run_id}/results        – all agent outputs
"""

import asyncio
import json as _json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel as _BaseModel

from app.config import settings
from app.db import crud
from app.db.models import PipelineRunDocument
from app.schemas.pipeline import (
    AGENT_STATUS_TO_FRONTEND,
    AgentRunResult,
    PipelineResultResponse,
    PipelineRunCreate,
    PipelineRunListItem,
    PipelineRunListResponse,
    PipelineRunResponse,
    PipelineStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


class PipelineActionResponse(_BaseModel):
    """Response schema for pipeline action endpoints (pause/resume/cancel)."""

    status: str
    run_id: str
    message: str


# Allowed file extensions and MIME types for uploaded documents
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
# Private helpers
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


async def _run_to_response(run: PipelineRunDocument) -> PipelineRunResponse:
    """Convert a :class:`~app.db.models.PipelineRunDocument` to the API response schema.

    Fetches all agent configs once and all results for the run, then builds
    the ``agent_runs`` list from the per-agent status map stored in the document.

    Args:
        run: The pipeline run document.

    Returns:
        A :class:`~app.schemas.pipeline.PipelineRunResponse` ready to serialise.
    """
    raw_statuses: dict[str, str] = run.agent_statuses  # native dict in Beanie

    agent_runs: list[AgentRunResult] = []

    if raw_statuses:
        all_configs = await crud.get_all_agent_configs()
        config_map = {c.agent_id: c for c in all_configs}

        all_results = await crud.get_pipeline_results(run.run_id)
        results_map: dict[str, str] = {}
        for r in all_results:
            preview = str(r.output)[:500] if r.output is not None else None
            results_map[r.agent_id] = preview or ""

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


async def _dag_run_to_response(run: PipelineRunDocument) -> PipelineRunResponse:
    """Convert a V3 PipelineRunDocument to PipelineRunResponse."""
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
        agent_runs=[],
    )


def _validate_upload(file: UploadFile) -> None:
    """Raise HTTP 422 if the uploaded file fails basic validation.

    Checks that the file has a filename and that the extension is in
    :data:`_ALLOWED_EXTENSIONS`.

    Args:
        file: The ``UploadFile`` received from the multipart form.

    Raises:
        HTTPException: 422 if the filename is missing.
        HTTPException: 415 if the extension is not supported.
    """
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

    Streams the file in 64 KB chunks and aborts with HTTP 413 if the total
    size exceeds :attr:`~app.config.Settings.MAX_FILE_SIZE_MB`.

    Args:
        file:   The ``UploadFile`` from the multipart form.
        run_id: UUID string used as the upload sub-directory name.

    Returns:
        ``(document_name, absolute_file_path)`` where *document_name* is the
        sanitised original filename.

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


def _result_to_response(r) -> PipelineResultResponse:
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
# Background task
# ─────────────────────────────────────────────────────────────────────────────


async def _run_pipeline_background(
    run_id: str,
    file_path: str,
    document_name: str,
    llm_profile_id: Optional[str],
    skip_execution: bool,
    environment: str,
) -> None:
    """Async background task that drives the full pipeline for one run.

    Steps:

    1. Wire the WebSocket broadcaster so live events reach connected clients.
    2. Mark the run as ``RUNNING`` in MongoDB.
    3. Invoke ``run_pipeline_async`` — the result is awaited directly (no
       thread-pool executor) since :class:`PipelineRunner` is now fully async.
    4. Update the run's terminal status based on the runner's return value.
       If a CANCEL signal is pending (set via :data:`signal_manager`), the run
       transitions to ``cancelled``; otherwise the runner's own status is used.

    Args:
        run_id:          UUID string of the pipeline run.
        file_path:       Absolute path to the saved requirements document.
        document_name:   Original filename (used in event payloads).
        llm_profile_id:  Optional MongoDB ObjectId string of the LLM profile
                         override, or ``None`` to use the global default.
        skip_execution:  When ``True``, skip the Execution and Reporting stages.
        environment:     Target test-environment name for the Execution crew.
    """
    import asyncio
    import json
    from datetime import datetime, timezone

    from app.api.v1.websocket import manager
    from app.core.pipeline_runner import run_pipeline_async
    from app.core.signal_manager import PipelineSignal, signal_manager

    logger.info(
        "[Pipeline] Background task started  run_id=%r  file=%r  profile=%s  "
        "skip_exec=%s  env=%r",
        run_id,
        file_path,
        llm_profile_id,
        skip_execution,
        environment,
    )

    # Refresh the event-loop reference on the WS manager so that
    # broadcast_from_thread() works correctly even if the manager was created
    # before this event loop started.
    current_loop = asyncio.get_running_loop()
    manager.set_loop(current_loop)

    # ── WebSocket broadcaster ────────────────────────────────────────────────

    def ws_broadcaster(event_type: str, data: dict[str, Any]) -> None:
        """Forward pipeline events to all WebSocket clients subscribed to *run_id*."""
        logger.debug(
            "[WS-TX] run_id=%r  event=%r  keys=%s",
            run_id,
            event_type,
            sorted(data.keys()),
        )
        payload = json.dumps(
            {
                "event": event_type,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            },
            default=str,
        )
        manager.broadcast_from_thread(run_id, payload)

    # Mark run as RUNNING so the UI can react immediately
    await crud.update_pipeline_status(
        run_id,
        PipelineStatus.RUNNING.value,
        started_at=datetime.now(timezone.utc),
    )

    try:
        result: dict[str, Any] = await run_pipeline_async(
            run_id=run_id,
            file_path=Path(file_path),
            document_name=document_name,
            run_profile_id=llm_profile_id,
            ws_broadcaster=ws_broadcaster,
            mock_mode=None,  # honour MOCK_CREWS env var
            environment=environment,
            skip_execution=skip_execution,
        )

        # ── Check for a pending CANCEL signal ───────────────────────────────
        pending_signal = await signal_manager.pop_signal(run_id)
        if pending_signal == PipelineSignal.CANCEL:
            await crud.update_pipeline_status(
                run_id,
                PipelineStatus.CANCELLED.value,
                error="Run was cancelled by user.",
            )
            ws_broadcaster("run.cancelled", {"message": "Pipeline cancelled by user."})
            logger.info("[Pipeline] Run cancelled  run_id=%r", run_id)
            return

        # ── Propagate the runner's reported status ───────────────────────────
        final_status_str: str = result.get("status", PipelineStatus.COMPLETED.value)
        try:
            final_status = PipelineStatus(final_status_str)
        except ValueError:
            final_status = PipelineStatus.COMPLETED

        error_msg: Optional[str] = result.get("error")
        await crud.update_pipeline_status(
            run_id,
            final_status.value,
            error=error_msg,
        )

        logger.info(
            "[Pipeline] Background task finished  run_id=%r  status=%s  duration=%.1fs",
            run_id,
            final_status.value,
            result.get("duration_seconds", 0),
        )

    except Exception as exc:
        # Clean up any pending signal so the registry does not grow unbounded
        await signal_manager.clear_signal(run_id)
        error_detail = str(exc)
        logger.exception(
            "[Pipeline] Unhandled error in background task  run_id=%r  error=%s",
            run_id,
            error_detail,
        )
        await crud.update_pipeline_status(
            run_id,
            PipelineStatus.FAILED.value,
            error=error_detail,
        )
        ws_broadcaster("run.failed", {"error": error_detail})


# ─────────────────────────────────────────────────────────────────────────────
# Background task (V3 – DAG runner)
# ─────────────────────────────────────────────────────────────────────────────


async def _run_dag_pipeline_background(
    run_id: str,
    template_id: str,
    file_path: Optional[str],
    document_name: str,
    llm_profile_id: Optional[str],
    run_params: dict,
) -> None:
    """Background task for the V3 DAG pipeline runner.

    Args:
        run_id:          UUID string of the pipeline run.
        template_id:     Slug of the pipeline template to execute.
        file_path:       Absolute path to the uploaded file (or None).
        document_name:   Original filename (used in event payloads).
        llm_profile_id:  Optional LLM profile override.
        run_params:      Extra run parameters from the request.
    """
    import json
    from datetime import datetime, timezone

    from app.api.v1.websocket import manager
    from app.core.dag_pipeline_runner import DAGPipelineRunner
    from app.core.dag_resolver import DAGValidationError
    from app.db import crud

    logger.info(
        "[V3-Pipeline] Background task started  run_id=%r  template=%r",
        run_id,
        template_id,
    )

    current_loop = asyncio.get_running_loop()
    manager.set_loop(current_loop)

    def ws_broadcaster(event_type: str, data: dict) -> None:
        """Forward pipeline events to WebSocket clients."""
        logger.debug("[WS-V3-TX] run_id=%r  event=%r", run_id, event_type)
        payload = json.dumps(
            {
                "event": event_type,
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            },
            default=str,
        )
        manager.broadcast_from_thread(run_id, payload)

    try:
        # Load template (might have been updated between request and execution)
        template = await crud.get_pipeline_template(template_id)
        if template is None:
            raise ValueError(f"Pipeline template '{template_id}' not found")

        runner = DAGPipelineRunner(
            run_id=run_id,
            template=template,
            llm_profile_id=llm_profile_id,
            progress_callback=ws_broadcaster,
            mock_mode=getattr(settings, "MOCK_PIPELINE", False),
        )

        initial_input = {
            "file_path": file_path,
            "document_name": document_name,
            **run_params,
        }
        await runner.run(initial_input)

    except DAGValidationError as exc:
        logger.error("[V3-Pipeline] DAG validation error  run_id=%r: %s", run_id, exc)
        await crud.update_pipeline_run(run_id, status="failed", error_message=str(exc))
        ws_broadcaster("run.failed", {"error": str(exc)})

    except Exception as exc:
        error_detail = str(exc)
        logger.exception(
            "[V3-Pipeline] Unhandled error  run_id=%r  error=%s", run_id, error_detail
        )
        await crud.update_pipeline_run(
            run_id, status="failed", error_message=error_detail
        )
        ws_broadcaster("run.failed", {"error": error_detail})


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline/run
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/run",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document and start a pipeline run",
    description=(
        "Accepts a multipart/form-data request containing the requirements document "
        "and optional run parameters. Returns immediately with ``status=pending``. "
        "Connect to ``WS /ws/pipeline/{run_id}`` to stream real-time progress "
        "events.\n\n"
        "**Supported file types:** PDF, TXT, MD, DOCX, HTML, CSV, RST\n\n"
        f"**Maximum file size:** {settings.MAX_FILE_SIZE_MB} MB"
    ),
)
async def start_pipeline_run(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Requirements document to analyse"),
    llm_profile_id: Optional[str] = Form(
        default=None,
        description=(
            "MongoDB ObjectId of the LLM profile to use for this run. "
            "Omit to use the global default profile."
        ),
    ),
    skip_execution: bool = Form(
        default=False,
        description=(
            "When true, only run Ingestion and Test Case Generation. "
            "Execution and Reporting stages will be skipped."
        ),
    ),
    environment: str = Form(
        default="default",
        description="Target test environment name passed to the Execution crew.",
    ),
) -> PipelineRunResponse:
    """Upload a requirements document and start a full pipeline run.

    The endpoint returns immediately with ``status=pending``.  The actual
    pipeline execution happens in a background task.  Clients should subscribe
    to the WebSocket endpoint at ``/ws/pipeline/{run_id}`` to receive live
    progress events.

    Args:
        background_tasks: FastAPI ``BackgroundTasks`` injected automatically.
        file:             Requirements document (PDF, DOCX, TXT, etc.).
        llm_profile_id:   Optional MongoDB ObjectId string of an LLM profile.
        skip_execution:   Skip Execution + Reporting stages when ``True``.
        environment:      Execution environment name forwarded to the crew.

    Returns:
        :class:`~app.schemas.pipeline.PipelineRunResponse` with
        ``status="pending"`` and the newly-created ``run_id``.

    Raises:
        HTTPException: 415 if the file type is not supported.
        HTTPException: 413 if the file exceeds ``MAX_FILE_SIZE_MB``.
        HTTPException: 404 if *llm_profile_id* does not exist.
        HTTPException: 429 if ``MAX_CONCURRENT_RUNS`` is already reached.
    """
    _validate_upload(file)

    # Validate the LLM profile override if provided
    if llm_profile_id is not None:
        profile = await crud.get_llm_profile(llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile with id={llm_profile_id!r} not found.",
            )

    # Check the concurrent-run limit
    _, running_count = await crud.get_all_pipeline_runs(
        skip=0, limit=1, status=PipelineStatus.RUNNING.value
    )
    if running_count >= settings.MAX_CONCURRENT_RUNS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Maximum concurrent runs ({settings.MAX_CONCURRENT_RUNS}) "
                "reached. Please wait for a running pipeline to complete."
            ),
        )

    # Generate run_id before saving the file so the upload path is deterministic
    run_id = str(uuid.uuid4())
    document_name, file_path = _save_upload(file, run_id)

    # Persist the run record in MongoDB
    run = await crud.create_pipeline_run(
        run_id=run_id,
        document_name=document_name,
        document_path=file_path,
        llm_profile_id=llm_profile_id,
    )

    logger.info(
        "[Pipeline] Created run  run_id=%r  document=%r  llm_profile=%s",
        run_id,
        document_name,
        llm_profile_id,
    )

    # Schedule the pipeline execution as a background task
    background_tasks.add_task(
        _run_pipeline_background,
        run_id=run_id,
        file_path=file_path,
        document_name=document_name,
        llm_profile_id=llm_profile_id,
        skip_execution=skip_execution,
        environment=environment,
    )

    return await _run_to_response(run)


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline/runs  (V3 – DAG runner)
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/runs",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="[V3] Start a DAG pipeline run from a template",
    description=(
        "Creates a new pipeline run based on a saved PipelineTemplate and starts "
        "DAG execution in the background.  Connect to "
        "``WS /ws/pipeline/{run_id}`` for real-time node/layer events.\n\n"
        "The template's DAG is validated before the run is created.  If validation "
        "fails, HTTP 422 is returned immediately.\n\n"
        "**V3 endpoint** — requires ``template_id``."
    ),
)
async def create_pipeline_run(
    background_tasks: BackgroundTasks,
    template_id: str = Form(
        ..., description="Slug of the pipeline template to execute"
    ),
    file: Optional[UploadFile] = File(
        default=None,
        description="Optional requirements document to inject as INPUT node seed",
    ),
    llm_profile_id: Optional[str] = Form(
        default=None,
        description="MongoDB ObjectId of an LLM profile override. Omit for global default.",
    ),
    run_params: str = Form(
        default="{}",
        description="JSON-encoded extra run parameters forwarded to the runner.",
    ),
) -> PipelineRunResponse:
    """Create and start a V3 DAG pipeline run.

    Returns immediately with ``status=pending``.  Execution happens in the
    background.  Listen on the WebSocket endpoint for live events.

    Args:
        background_tasks: FastAPI injected background task queue.
        template_id:      Slug of the target pipeline template.
        file:             Optional uploaded requirements document.
        llm_profile_id:   Optional LLM profile ObjectId string.
        run_params:       JSON-encoded dict of extra run parameters.

    Returns:
        PipelineRunResponse with ``status="pending"`` and the new ``run_id``.

    Raises:
        HTTPException 404: Template not found.
        HTTPException 400: Template is archived.
        HTTPException 422: DAG validation failed or run_params not valid JSON.
        HTTPException 404: llm_profile_id not found.
        HTTPException 429: Maximum concurrent runs reached.
    """
    from app.core.dag_resolver import DAGResolver, DAGValidationError
    from app.db import crud as _crud

    # ── Validate JSON run_params ─────────────────────────────────────────────
    try:
        parsed_run_params: dict = _json.loads(run_params)
    except _json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"run_params is not valid JSON: {exc}",
        )

    # ── Load and check template ──────────────────────────────────────────────
    template = await _crud.get_pipeline_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline template '{template_id}' not found.",
        )
    if template.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pipeline template '{template_id}' is archived and cannot be run.",
        )

    # ── Validate the DAG eagerly (fail fast before creating any DB records) ──
    resolver = DAGResolver(template.nodes, template.edges)
    try:
        resolver.validate()
    except DAGValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pipeline DAG is invalid: {exc}",
        )

    # ── Validate LLM profile override (if provided) ──────────────────────────
    if llm_profile_id is not None:
        profile = await _crud.get_llm_profile(llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile '{llm_profile_id}' not found.",
            )

    # ── Check concurrent-run limit ────────────────────────────────────────────
    _, running_count = await _crud.get_all_pipeline_runs(
        skip=0, limit=1, status=PipelineStatus.RUNNING.value
    )
    if running_count >= settings.MAX_CONCURRENT_RUNS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Maximum concurrent runs ({settings.MAX_CONCURRENT_RUNS}) reached. "
                "Please wait for a running pipeline to complete."
            ),
        )

    # ── Handle optional file upload ───────────────────────────────────────────
    run_id = str(uuid.uuid4())
    file_path: Optional[str] = None
    document_name: str = ""

    if file and file.filename:
        _validate_upload(file)
        document_name, file_path = _save_upload(file, run_id)

    # ── Persist run record ────────────────────────────────────────────────────
    run = await _crud.create_dag_run(
        run_id=run_id,
        template_id=template_id,
        template_snapshot={
            "nodes": [n.model_dump() for n in template.nodes],
            "edges": [e.model_dump() for e in template.edges],
        },
        document_name=document_name,
        file_path=file_path,
        llm_profile_id=llm_profile_id,
        run_params=parsed_run_params,
    )

    logger.info(
        "[V3-Pipeline] Created run  run_id=%r  template=%r  document=%r",
        run_id,
        template_id,
        document_name or "(none)",
    )

    # ── Schedule DAG execution ────────────────────────────────────────────────
    background_tasks.add_task(
        _run_dag_pipeline_background,
        run_id=run_id,
        template_id=template_id,
        file_path=file_path,
        document_name=document_name,
        llm_profile_id=llm_profile_id,
        run_params=parsed_run_params,
    )

    return await _dag_run_to_response(run)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs",
    response_model=PipelineRunListResponse,
    summary="List pipeline runs",
    description=(
        "Returns a paginated list of pipeline runs ordered by creation time "
        "(newest first). Optionally filter by status."
    ),
)
async def list_pipeline_runs(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description=(
            "Filter by status: pending | running | paused | "
            "completed | failed | cancelled"
        ),
    ),
    template_id: Optional[str] = Query(
        default=None,
        description="Filter runs by pipeline template ID",
    ),
) -> PipelineRunListResponse:
    """Return a paginated list of pipeline runs.

    Args:
        page:          1-based page number.
        page_size:     Number of items per page (max 100).
        status_filter: Optional status value to filter by.

    Returns:
        :class:`~app.schemas.pipeline.PipelineRunListResponse` with
        ``items``, ``total``, ``page``, and ``page_size``.

    Raises:
        HTTPException: 422 if *status_filter* is not a valid
            :class:`~app.schemas.pipeline.PipelineStatus` value.
    """
    if status_filter is not None:
        try:
            PipelineStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid status filter '{status_filter}'. "
                    f"Valid values: {[s.value for s in PipelineStatus]}"
                ),
            )

    skip = (page - 1) * page_size
    runs, total = await crud.get_all_pipeline_runs(
        skip=skip,
        limit=page_size,
        status=status_filter,
        template_id=template_id,
    )

    # Fetch agent configs once for display-name enrichment
    all_configs = await crud.get_all_agent_configs()
    config_map = {c.agent_id: c for c in all_configs}

    items: list[PipelineRunListItem] = []
    for r in runs:
        items.append(
            PipelineRunListItem(
                id=r.run_id,
                document_filename=r.document_name,
                status=PipelineStatus(r.status),
                llm_profile_id=r.llm_profile_id,
                current_stage=r.current_stage,
                created_at=r.created_at,
                started_at=r.started_at,
                completed_at=r.finished_at,
                error_message=r.error,
            )
        )
    # Suppress unused variable warning — config_map kept for future enrichment
    _ = config_map

    return PipelineRunListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/{run_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}",
    summary="Get pipeline run detail",
    description=(
        "Returns the full detail for a single pipeline run including "
        "per-agent statuses and all persisted agent outputs."
    ),
)
async def get_pipeline_run(
    run_id: str,
    include_results: bool = Query(
        default=True,
        description="Include individual agent outputs in the response",
    ),
    stage: Optional[str] = Query(
        default=None,
        description=(
            "Filter results by stage: ingestion | testcase | execution | reporting"
        ),
    ),
) -> dict[str, Any]:
    """Retrieve the full detail of a single pipeline run.

    Args:
        run_id:          UUID string of the run.
        include_results: When ``True`` (the default), agent output documents
                         are embedded in the response under ``"results"``.
        stage:           If provided, restrict embedded results to this stage.

    Returns:
        A dict representation of
        :class:`~app.schemas.pipeline.PipelineRunResponse` optionally extended
        with a ``"results"`` key containing per-agent outputs.

    Raises:
        HTTPException: 404 if the run does not exist.
    """
    run = await _get_run_or_404(run_id)
    run_response = await _run_to_response(run)
    response: dict[str, Any] = run_response.model_dump()

    if include_results:
        raw_results = await crud.get_pipeline_results(run_id, stage=stage)
        response["results"] = [
            PipelineResultResponse(
                id=str(r.id),
                run_id=r.run_id,
                stage=r.stage,
                agent_id=r.agent_id,
                output=r.output,
                created_at=r.created_at,
            ).model_dump()
            for r in raw_results
        ]

    return response


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /pipeline/runs/{run_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a pipeline run",
    description=(
        "Deletes the pipeline run record and all associated agent results. "
        "Also removes the uploaded document from disk. "
        "Running pipelines should be cancelled before deletion."
    ),
)
async def delete_pipeline_run(run_id: str) -> None:
    """Delete a pipeline run and all its associated data.

    If the run is currently executing, a CANCEL signal is sent via
    :data:`~app.core.signal_manager.signal_manager` so the background task
    stops as soon as possible before the DB records are removed.

    Args:
        run_id: UUID string of the run to delete.

    Raises:
        HTTPException: 404 if the run does not exist.
    """
    from app.core.signal_manager import PipelineSignal, signal_manager

    run = await _get_run_or_404(run_id)

    if run.status in (PipelineStatus.RUNNING.value, PipelineStatus.PAUSED.value):
        logger.warning(
            "[Pipeline] Deleting a %s run  run_id=%r — "
            "the background task may still be writing results.",
            run.status.upper(),
            run_id,
        )
        await signal_manager.set_signal(run_id, PipelineSignal.CANCEL)

    # Remove uploaded files from disk
    upload_dir = Path(settings.UPLOAD_DIR) / run_id
    if upload_dir.exists():
        try:
            shutil.rmtree(upload_dir)
            logger.info("[Pipeline] Removed upload dir %s", upload_dir)
        except Exception as exc:
            logger.warning(
                "[Pipeline] Could not remove upload dir %s: %s", upload_dir, exc
            )

    deleted = await crud.delete_pipeline_run(run_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )
    logger.info("[Pipeline] Deleted run  run_id=%r", run_id)


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline/runs/{run_id}/pause
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/runs/{run_id}/pause",
    response_model=PipelineActionResponse,
    summary="Pause a running pipeline",
    description=(
        "Requests that the pipeline pause after its current stage completes. "
        "The run transitions to ``paused`` status at the next safe checkpoint. "
        "Only runs with ``status=running`` can be paused."
    ),
)
async def pause_pipeline(run_id: str) -> PipelineActionResponse:
    """Request that a running pipeline pause after the current stage.

    Sets a PAUSE signal via :data:`~app.core.signal_manager.signal_manager`.
    The pipeline runner polls the signal at stage boundaries and will
    transition the run to ``paused`` status when it honours the request.

    Args:
        run_id: UUID string of the pipeline run to pause.

    Returns:
        Acknowledgement dict with ``status``, ``run_id``, and ``message``.

    Raises:
        HTTPException: 404 if the run does not exist.
        HTTPException: 400 if the run is not currently in ``running`` status.
    """
    from app.core.signal_manager import PipelineSignal, signal_manager

    run = await crud.get_pipeline_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )
    if run.status != PipelineStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause a '{run.status}' pipeline. Only 'running' pipelines can be paused.",
        )

    await signal_manager.set_signal(run_id, PipelineSignal.PAUSE)
    logger.info("[Pipeline] Pause requested  run_id=%r", run_id)
    return PipelineActionResponse(
        status="pause_requested",
        run_id=run_id,
        message="Pipeline will pause after the current stage completes.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline/runs/{run_id}/resume
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/runs/{run_id}/resume",
    response_model=PipelineActionResponse,
    summary="Resume a paused pipeline",
    description=(
        "Requests that a paused pipeline continue execution from where it left off. "
        "Only runs with ``status=paused`` can be resumed."
    ),
)
async def resume_pipeline(run_id: str) -> PipelineActionResponse:
    """Request that a paused pipeline resume execution.

    Sets a RESUME signal via :data:`~app.core.signal_manager.signal_manager`.
    The pipeline runner's pause-loop polls this signal and will wake up and
    continue to the next stage when it detects ``PipelineSignal.RESUME``.

    Args:
        run_id: UUID string of the pipeline run to resume.

    Returns:
        Acknowledgement dict with ``status`` and ``run_id``.

    Raises:
        HTTPException: 404 if the run does not exist.
        HTTPException: 400 if the run is not currently in ``paused`` status.
    """
    from app.core.signal_manager import PipelineSignal, signal_manager

    run = await crud.get_pipeline_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )
    if run.status != PipelineStatus.PAUSED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resume a '{run.status}' pipeline. Only 'paused' pipelines can be resumed.",
        )

    await signal_manager.set_signal(run_id, PipelineSignal.RESUME)
    logger.info("[Pipeline] Resume requested  run_id=%r", run_id)
    return PipelineActionResponse(
        status="resume_requested",
        run_id=run_id,
        message="Pipeline will resume from where it left off.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline/runs/{run_id}/cancel
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/runs/{run_id}/cancel",
    response_model=PipelineActionResponse,
    summary="Cancel a running or paused pipeline",
    description=(
        "Requests cancellation of a pipeline that is currently ``running``, "
        "``paused``, or ``pending``.  The background task (or pause-loop) will "
        "honour the signal at the next checkpoint and transition the run to "
        "``cancelled`` status.  Runs already in a terminal state cannot be "
        "cancelled."
    ),
)
async def cancel_pipeline(run_id: str) -> PipelineActionResponse:
    """Request cancellation of a running, paused, or pending pipeline.

    * **PENDING** / **RUNNING** / **PAUSED** runs receive a CANCEL signal via
      :data:`~app.core.signal_manager.signal_manager`.  The background task
      will transition them to ``cancelled`` at the next safe checkpoint.
    * **Terminal** runs (completed / failed / cancelled) cannot be cancelled.

    Args:
        run_id: UUID string of the run to cancel.

    Returns:
        Acknowledgement dict with ``status`` and ``run_id``.

    Raises:
        HTTPException: 404 if the run does not exist.
        HTTPException: 400 if the run is already in a terminal state.
    """
    from app.core.signal_manager import PipelineSignal, signal_manager

    run = await crud.get_pipeline_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )

    _terminal = {
        PipelineStatus.COMPLETED.value,
        PipelineStatus.FAILED.value,
        PipelineStatus.CANCELLED.value,
    }
    if run.status in _terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot cancel run '{run_id}': it has already reached "
                f"terminal status '{run.status}'."
            ),
        )

    await signal_manager.set_signal(run_id, PipelineSignal.CANCEL)
    logger.info("[Pipeline] Cancellation requested  run_id=%r", run_id)
    return PipelineActionResponse(
        status="cancel_requested",
        run_id=run_id,
        message="Cancellation signal sent. The pipeline will stop at the next checkpoint.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/{run_id}/results
# ─────────────────────────────────────────────────────────────────────────────


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
        description=("Filter by stage: ingestion | testcase | execution | reporting"),
    ),
    agent_id: Optional[str] = Query(
        default=None,
        description="Filter by agent slug, e.g. 'requirement_analyzer'",
    ),
) -> list[PipelineResultResponse]:
    """Retrieve all agent output documents for a run.

    Args:
        run_id:    UUID string of the run.
        stage:     Optional stage filter.
        agent_id:  Optional agent slug filter.

    Returns:
        List of :class:`~app.schemas.pipeline.PipelineResultResponse` ordered
        by creation time (oldest first).

    Raises:
        HTTPException: 404 if the run does not exist.
    """
    await _get_run_or_404(run_id)  # verify run exists first

    raw_results = await crud.get_pipeline_results(
        run_id, stage=stage, agent_id=agent_id
    )
    return [
        PipelineResultResponse(
            id=str(r.id),
            run_id=r.run_id,
            stage=r.stage,
            agent_id=r.agent_id,
            output=r.output,
            created_at=r.created_at,
        )
        for r in raw_results
    ]


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/{run_id}/results/{node_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/results/{node_id}",
    response_model=PipelineResultResponse,
    summary="Get result for a specific node in a pipeline run",
    description=(
        "Returns the persisted output of a single DAG node for the given run. "
        "Uses the ``node_id`` field from the pipeline result document."
    ),
)
async def get_node_result(run_id: str, node_id: str) -> PipelineResultResponse:
    """Retrieve the output of a specific node in a pipeline run.

    Args:
        run_id:  UUID string of the run.
        node_id: DAG node ID to retrieve the result for.

    Returns:
        A :class:`~app.schemas.pipeline.PipelineResultResponse`.

    Raises:
        HTTPException: 404 if no result exists for this node/run combination.
    """
    result = await crud.get_pipeline_result_by_node(run_id, node_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No result found for node '{node_id}' in run '{run_id}'.",
        )
    return _result_to_response(result)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/{run_id}/export/html
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/export/html",
    summary="Download pipeline report as HTML",
    description="Generates a self-contained HTML report for a completed pipeline run.",
    response_class=Response,
)
async def export_report_html(run_id: str) -> Response:
    """Download the pipeline report as a self-contained HTML file.

    Args:
        run_id: UUID string of the run.

    Returns:
        HTML file as a download response.

    Raises:
        HTTPException: 404 if the run does not exist.
        HTTPException: 400 if the run has no results yet.
    """
    from fastapi.responses import Response as FastAPIResponse

    from app.services.export_service import ExportService

    await _get_run_or_404(run_id)
    try:
        service = ExportService(run_id)
        html_bytes = await service.export_html()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    filename = f"auto-at-report-{run_id[:8]}.html"
    return FastAPIResponse(
        content=html_bytes,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/{run_id}/export/docx
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/export/docx",
    summary="Download pipeline report as DOCX",
    description="Generates a Microsoft Word DOCX report for a completed pipeline run.",
    response_class=Response,
)
async def export_report_docx(run_id: str) -> Response:
    """Download the pipeline report as a DOCX (Microsoft Word) file.

    Args:
        run_id: UUID string of the run.

    Returns:
        DOCX file as a download response.

    Raises:
        HTTPException: 404 if the run does not exist.
        HTTPException: 400 if the run has no results yet.
    """
    from fastapi.responses import Response as FastAPIResponse

    from app.services.export_service import ExportService

    await _get_run_or_404(run_id)
    try:
        service = ExportService(run_id)
        docx_bytes = await service.export_docx()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    filename = f"auto-at-report-{run_id[:8]}.docx"
    return FastAPIResponse(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
