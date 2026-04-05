from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.config import settings
from app.db import crud
from app.schemas.pipeline import (
    AGENT_STATUS_TO_FRONTEND,
    AgentRunResult,
    AgentRunStatus,
    PipelineResultResponse,
    PipelineRunListItem,
    PipelineRunListResponse,
    PipelineRunResponse,
    PipelineStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

# ─────────────────────────────────────────────────────────────────────────────
# Dependency alias
# ─────────────────────────────────────────────────────────────────────────────

DB = Annotated[Session, Depends(get_db)]

# ─────────────────────────────────────────────────────────────────────────────
# In-memory cancellation registry
#
# When a client calls  POST /pipeline/runs/{run_id}/cancel  we add the run_id
# here.  The pipeline background task checks this set periodically and aborts
# gracefully.  The set is cleared once the run reaches a terminal state.
# ─────────────────────────────────────────────────────────────────────────────

_CANCEL_REQUESTED: set[str] = set()

# Allowed MIME types / file extensions for uploaded documents
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
    "application/octet-stream",  # generic fallback browsers sometimes send
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_run_or_404(db: Session, run_id: str):
    """Return PipelineRun ORM object or raise HTTP 404."""
    run = crud.get_pipeline_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )
    return run


def _orm_run_to_response(run, db: Session) -> PipelineRunResponse:
    """Convert a PipelineRun ORM instance to PipelineRunResponse."""
    raw_statuses: dict[str, str] = run.get_agent_statuses()

    # Build agent_runs from agent configs + statuses + results
    agent_runs: list[AgentRunResult] = []

    if raw_statuses:
        # Get all agent configs for display names and stages
        all_configs = crud.get_all_agent_configs(db)
        config_map = {c.agent_id: c for c in all_configs}

        # Get all results for output previews
        all_results = crud.get_pipeline_results(db, run.id)
        results_map: dict[str, str] = {}
        for r in all_results:
            out = r.get_output()
            preview = str(out)[:500] if out else None
            results_map[r.agent_id] = preview

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
        id=run.id,
        document_filename=run.document_name,
        status=PipelineStatus(run.status),
        agent_runs=agent_runs,
        error_message=run.error,
        llm_profile_id=run.llm_profile_id,
        created_at=run.created_at,
        started_at=run.created_at,
        completed_at=run.finished_at,
    )


def _validate_upload(file: UploadFile) -> None:
    """Raise HTTP 422 if the uploaded file fails basic validation."""
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
    """
    Persist the uploaded file to UPLOAD_DIR/<run_id>/<original_filename>.

    Returns:
        (document_name, absolute_file_path)

    Raises:
        HTTPException 413 if the file exceeds MAX_FILE_SIZE_MB.
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
                chunk = file.file.read(64 * 1024)  # 64 KB chunks
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


# ─────────────────────────────────────────────────────────────────────────────
# Background task
# ─────────────────────────────────────────────────────────────────────────────


async def _run_pipeline_background(
    run_id: str,
    file_path: str,
    document_name: str,
    llm_profile_id: Optional[int],
    skip_execution: bool,
    environment: str,
) -> None:
    """
    Async background task that drives the full pipeline for one run.

    Steps:
    1. Open a fresh DB session (the request session has been closed).
    2. Wire the WebSocket broadcaster so events flow to connected clients.
    3. Invoke ``run_pipeline_async`` in a thread-pool executor.
    4. Update the run's terminal status based on the result.
    5. Clean up the uploaded file if the run folder should be kept.
    """
    import asyncio

    # Import here to avoid circular imports at module load time
    from app.api.v1.websocket import manager
    from app.core.pipeline_runner import run_pipeline_async
    from app.db.database import SessionLocal

    logger.info(
        "[Pipeline] Background task started  run_id=%r  file=%r  profile=%s  skip_exec=%s  env=%r",
        run_id,
        file_path,
        llm_profile_id,
        skip_execution,
        environment,
    )

    # Refresh the event loop reference on the WS manager.  The lifespan hook
    # already does this at startup, but refreshing here costs nothing and
    # guarantees correctness if the manager is ever reset between restarts.
    current_loop = asyncio.get_running_loop()
    manager.set_loop(current_loop)
    logger.debug(
        "[Pipeline] WS manager loop refreshed  run_id=%r  loop=%r", run_id, current_loop
    )

    # ── Build a WS broadcaster that is safe to call from a thread ────────────

    def ws_broadcaster(event_type: str, data: dict[str, Any]) -> None:
        """Called by PipelineRunner (inside executor thread) for every event."""
        import json
        from datetime import datetime, timezone

        # Log every outgoing event so we can trace what is actually emitted.
        logger.debug(
            "[WS-TX] run_id=%r  event=%r  data_keys=%s",
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

    with SessionLocal() as db:
        # Mark run as RUNNING immediately so the UI can react
        crud.update_pipeline_run_status(db, run_id, PipelineStatus.RUNNING)

        try:
            result: dict[str, Any] = await run_pipeline_async(
                db=db,
                run_id=run_id,
                file_path=Path(file_path),
                document_name=document_name,
                run_profile_id=llm_profile_id,
                ws_broadcaster=ws_broadcaster,
                mock_mode=None,  # honour MOCK_CREWS env var
                environment=environment,
                skip_execution=skip_execution,
            )

            # Check if cancellation was requested while pipeline ran
            if run_id in _CANCEL_REQUESTED:
                _CANCEL_REQUESTED.discard(run_id)
                crud.update_pipeline_run_status(
                    db,
                    run_id,
                    PipelineStatus.FAILED,
                    error="Run was cancelled by user.",
                )
                logger.info("[Pipeline] Run cancelled  run_id=%r", run_id)
                return

            # Propagate the runner's reported status
            final_status_str: str = result.get("status", "completed")
            try:
                final_status = PipelineStatus(final_status_str)
            except ValueError:
                final_status = PipelineStatus.COMPLETED

            error_msg: Optional[str] = result.get("error")

            crud.update_pipeline_run_status(
                db,
                run_id,
                final_status,
                error=error_msg,
            )

            logger.info(
                "[Pipeline] Background task finished  run_id=%r  status=%s  duration=%.1fs",
                run_id,
                final_status,
                result.get("duration_seconds", 0),
            )

        except Exception as exc:
            _CANCEL_REQUESTED.discard(run_id)
            error_detail = str(exc)
            logger.exception(
                "[Pipeline] Unhandled error in background task  run_id=%r  error=%s",
                run_id,
                error_detail,
            )
            crud.update_pipeline_run_status(
                db,
                run_id,
                PipelineStatus.FAILED,
                error=error_detail,
            )

            # Broadcast failure event to any listening WS clients
            ws_broadcaster(
                "run.failed",
                {"error": error_detail},
            )


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
        "and optional run parameters. Returns immediately with a `run_id` and "
        "`status=pending`. Connect to `WS /ws/pipeline/{run_id}` to stream "
        "real-time progress events.\n\n"
        "**Supported file types:** PDF, TXT, MD, DOCX, HTML, CSV, RST\n\n"
        f"**Maximum file size:** {settings.MAX_FILE_SIZE_MB} MB"
    ),
)
async def start_pipeline_run(
    background_tasks: BackgroundTasks,
    db: DB,
    file: UploadFile = File(..., description="Requirements document to analyse"),
    llm_profile_id: Optional[int] = Form(
        default=None,
        description=(
            "Override LLM profile for this run. Omit to use the global default profile."
        ),
    ),
    skip_execution: bool = Form(
        default=False,
        description=(
            "When true, only run Ingestion and Test Case Generation stages. "
            "Execution and Reporting will be skipped."
        ),
    ),
    environment: str = Form(
        default="default",
        description="Target test environment name passed to the Execution crew.",
    ),
) -> PipelineRunResponse:
    # ── Validate the uploaded file ────────────────────────────────────────────
    _validate_upload(file)

    # ── Validate llm_profile_id if provided ──────────────────────────────────
    if llm_profile_id is not None:
        profile = crud.get_llm_profile(db, llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile with id={llm_profile_id} not found.",
            )

    # ── Check concurrent run limit ────────────────────────────────────────────
    _, running_count = crud.get_all_pipeline_runs(
        db, skip=0, limit=1, status=PipelineStatus.RUNNING.value
    )
    if running_count >= settings.MAX_CONCURRENT_RUNS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Maximum concurrent runs ({settings.MAX_CONCURRENT_RUNS}) reached. "
                "Please wait for a running pipeline to complete before starting a new one."
            ),
        )

    # ── Generate run_id and save the upload ───────────────────────────────────
    run_id = str(uuid.uuid4())
    document_name, file_path = _save_upload(file, run_id)

    # ── Create the DB record ─────────────────────────────────────────────────
    run = crud.create_pipeline_run(
        db,
        document_name=document_name,
        document_path=file_path,
        llm_profile_id=llm_profile_id,
    )
    # Override the auto-generated id with our pre-computed one so the WS URL
    # is known before the background task starts
    # (create_pipeline_run already uses uuid internally but we need consistency)
    # Actually: reassign the run_id to match our pre-generated one
    run_id = run.id  # use the id that was written to DB

    logger.info(
        "[Pipeline] Created run  id=%r  document=%r  llm_profile=%s",
        run_id,
        document_name,
        llm_profile_id,
    )

    # ── Schedule background pipeline execution ────────────────────────────────
    background_tasks.add_task(
        _run_pipeline_background,
        run_id=run_id,
        file_path=file_path,
        document_name=document_name,
        llm_profile_id=llm_profile_id,
        skip_execution=skip_execution,
        environment=environment,
    )

    return _orm_run_to_response(run, db)


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
def list_pipeline_runs(
    db: DB,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: pending | running | completed | failed",
    ),
) -> PipelineRunListResponse:
    # Validate status filter
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
    runs, total = crud.get_all_pipeline_runs(
        db,
        skip=skip,
        limit=page_size,
        status=status_filter,
    )

    # Get agent configs once for building agent_runs
    all_configs = crud.get_all_agent_configs(db)
    config_map = {c.agent_id: c for c in all_configs}

    items = []
    for r in runs:
        raw_statuses = r.get_agent_statuses()
        all_results = crud.get_pipeline_results(db, r.id)
        results_map = {
            res.agent_id: str(res.get_output())[:500] if res.get_output() else None
            for res in all_results
        }

        agent_runs = []
        for agent_id, raw_status in raw_statuses.items():
            config = config_map.get(agent_id)
            agent_runs.append(
                AgentRunResult(
                    agent_id=agent_id,
                    display_name=config.display_name if config else agent_id,
                    stage=config.stage if config else "ingestion",
                    status=AGENT_STATUS_TO_FRONTEND.get(raw_status, "pending"),
                    output_preview=results_map.get(agent_id),
                )
            )

        items.append(
            PipelineRunListItem(
                id=r.id,
                document_filename=r.document_name,
                status=PipelineStatus(r.status),
                llm_profile_id=r.llm_profile_id,
                created_at=r.created_at,
                started_at=r.created_at,
                completed_at=r.finished_at,
                error_message=r.error,
                agent_runs=agent_runs,
            )
        )

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
def get_pipeline_run(
    db: DB,
    run_id: str,
    include_results: bool = Query(
        default=True,
        description="Include individual agent outputs in the response",
    ),
    stage: Optional[str] = Query(
        default=None,
        description="Filter results by stage: ingestion | testcase | execution | reporting",
    ),
) -> dict[str, Any]:
    run = _get_run_or_404(db, run_id)
    run_response = _orm_run_to_response(run, db)

    response: dict[str, Any] = run_response.model_dump()

    # Attach agent results if requested
    if include_results:
        raw_results = crud.get_pipeline_results(db, run_id, stage=stage)
        results = []
        for r in raw_results:
            results.append(
                PipelineResultResponse(
                    id=r.id,
                    run_id=r.run_id,
                    stage=r.stage,
                    agent_id=r.agent_id,
                    output=r.get_output(),
                    created_at=r.created_at,
                ).model_dump()
            )
        response["results"] = results

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
def delete_pipeline_run(db: DB, run_id: str) -> None:
    run = _get_run_or_404(db, run_id)

    # Warn if still running — we allow deletion but log a warning
    if run.status == PipelineStatus.RUNNING.value:
        logger.warning(
            "[Pipeline] Deleting a RUNNING run  run_id=%r  — "
            "the background task may still be writing results.",
            run_id,
        )
        # Request cancellation so the background task stops as soon as possible
        _CANCEL_REQUESTED.add(run_id)

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

    deleted = crud.delete_pipeline_run(db, run_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run '{run_id}' not found.",
        )
    logger.info("[Pipeline] Deleted run  run_id=%r", run_id)


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline/runs/{run_id}/cancel
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/runs/{run_id}/cancel",
    response_model=PipelineRunResponse,
    summary="Request cancellation of a running pipeline",
    description=(
        "Marks the run for cancellation. The background task will stop at the "
        "next safe checkpoint and transition the run to `failed` status with "
        "message 'Run was cancelled by user.'. "
        "Has no effect if the run is already in a terminal state "
        "(completed / failed)."
    ),
)
def cancel_pipeline_run(db: DB, run_id: str) -> PipelineRunResponse:
    run = _get_run_or_404(db, run_id)

    current_status = PipelineStatus(run.status)

    if current_status in (PipelineStatus.COMPLETED, PipelineStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot cancel run '{run_id}': "
                f"it has already reached terminal status '{current_status.value}'."
            ),
        )

    if current_status == PipelineStatus.PENDING:
        # Run hasn't started yet — mark it failed immediately
        updated = crud.update_pipeline_run_status(
            db,
            run_id,
            PipelineStatus.FAILED,
            error="Run was cancelled by user before it started.",
        )
        logger.info("[Pipeline] Cancelled PENDING run  run_id=%r", run_id)
        return _orm_run_to_response(updated, db)

    # RUNNING — register the cancellation request; background task will honour it
    _CANCEL_REQUESTED.add(run_id)
    logger.info("[Pipeline] Cancellation requested  run_id=%r", run_id)

    # Re-fetch to return the latest state
    run = crud.get_pipeline_run(db, run_id)
    return _orm_run_to_response(run, db)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/{run_id}/results
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/results",
    response_model=list[PipelineResultResponse],
    summary="Get all agent outputs for a pipeline run",
    description=(
        "Returns the persisted output of every agent for the given run, "
        "ordered by creation time. Optionally filter by `stage` or `agent_id`."
    ),
)
def get_pipeline_results(
    db: DB,
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
    _get_run_or_404(db, run_id)  # ensure run exists

    raw_results = crud.get_pipeline_results(db, run_id, stage=stage, agent_id=agent_id)
    return [
        PipelineResultResponse(
            id=r.id,
            run_id=r.run_id,
            stage=r.stage,
            agent_id=r.agent_id,
            output=r.get_output(),
            created_at=r.created_at,
        )
        for r in raw_results
    ]
