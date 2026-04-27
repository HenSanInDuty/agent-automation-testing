from __future__ import annotations

"""
pipeline/runs.py – CRUD endpoints for pipeline run management.

Endpoints:
    POST   /pipeline/run          – upload document + start V2 run
    POST   /pipeline/runs         – [V3] start DAG pipeline run from template
    GET    /pipeline/runs         – paginated list of runs
    GET    /pipeline/runs/{run_id} – get one run (with results)
    DELETE /pipeline/runs/{run_id} – delete run + files
"""

import json as _json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    status,
    UploadFile,
)

from app.config import settings
from app.db import crud
from app.schemas.pipeline import (
    PipelineResultResponse,
    PipelineRunCreate,
    PipelineRunListItem,
    PipelineRunListResponse,
    PipelineRunResponse,
    PipelineStatus,
)

from ._background import _run_dag_pipeline_background, _run_pipeline_background
from ._helpers import (
    _dag_run_to_response,
    _get_run_or_404,
    _run_to_response,
    _save_upload,
    _validate_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# POST /pipeline/run  (V2 legacy)
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
    file: Annotated[UploadFile, File(description="Requirements document to analyse")],
    llm_profile_id: Annotated[
        Optional[str],
        Form(
            description=(
                "MongoDB ObjectId of the LLM profile to use for this run. "
                "Omit to use the global default profile."
            ),
        ),
    ] = None,
    skip_execution: Annotated[
        bool,
        Form(
            description=(
                "When true, only run Ingestion and Test Case Generation. "
                "Execution and Reporting stages will be skipped."
            ),
        ),
    ] = False,
    environment: Annotated[
        str,
        Form(description="Target test environment name passed to the Execution crew."),
    ] = "default",
) -> PipelineRunResponse:
    """Upload a requirements document and start a full V2 pipeline run."""
    _validate_upload(file)

    if llm_profile_id is not None:
        profile = await crud.get_llm_profile(llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile with id={llm_profile_id!r} not found.",
            )

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

    run_id = str(uuid.uuid4())
    document_name, file_path = _save_upload(file, run_id)

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
    template_id: Annotated[str, Form(description="Slug of the pipeline template to execute")],
    file: Annotated[
        Optional[UploadFile],
        File(description="Optional requirements document to inject as INPUT node seed"),
    ] = None,
    llm_profile_id: Annotated[
        Optional[str],
        Form(description="MongoDB ObjectId of an LLM profile override. Omit for global default."),
    ] = None,
    run_params: Annotated[
        str,
        Form(description="JSON-encoded extra run parameters forwarded to the runner."),
    ] = "{}",
) -> PipelineRunResponse:
    """Create and start a V3 DAG pipeline run."""
    from app.core.dag_resolver import DAGResolver, DAGValidationError
    from app.db import crud as _crud

    try:
        parsed_run_params: dict = _json.loads(run_params)
    except _json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"run_params is not valid JSON: {exc}",
        )

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

    resolver = DAGResolver(template.nodes, template.edges)
    try:
        resolver.validate()
    except DAGValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pipeline DAG is invalid: {exc}",
        )

    if llm_profile_id is not None:
        profile = await _crud.get_llm_profile(llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile '{llm_profile_id}' not found.",
            )

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

    run_id = str(uuid.uuid4())
    file_path: Optional[str] = None
    document_name: str = ""

    if file and file.filename:
        _validate_upload(file)
        document_name, file_path = _save_upload(file, run_id)

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
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status_filter: Annotated[
        Optional[str],
        Query(
            alias="status",
            description=(
                "Filter by status: pending | running | paused | "
                "completed | failed | cancelled"
            ),
        ),
    ] = None,
    template_id: Annotated[
        Optional[str],
        Query(description="Filter runs by pipeline template ID"),
    ] = None,
) -> PipelineRunListResponse:
    """Return a paginated list of pipeline runs."""
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

    all_configs = await crud.get_all_agent_configs()
    config_map = {c.agent_id: c for c in all_configs}

    items: list[PipelineRunListItem] = []
    for r in runs:
        items.append(
            PipelineRunListItem(
                id=r.run_id,
                template_id=r.template_id,
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
    include_results: Annotated[
        bool,
        Query(description="Include individual agent outputs in the response"),
    ] = True,
    stage: Annotated[
        Optional[str],
        Query(description="Filter results by stage: ingestion | testcase | execution | reporting"),
    ] = None,
) -> dict[str, Any]:
    """Retrieve the full detail of a single pipeline run."""
    run = await _get_run_or_404(run_id)
    if run.template_id:
        run_response = await _dag_run_to_response(run)
    else:
        run_response = await _run_to_response(run)
    response: dict[str, Any] = run_response.model_dump()

    if include_results:
        raw_results = await crud.get_pipeline_results(run_id, stage=stage)
        response["results"] = [
            PipelineResultResponse(
                id=str(r.id),
                run_id=r.run_id,
                stage=r.stage or "",
                agent_id=r.agent_id or "",
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
    """Delete a pipeline run and all its associated data."""
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
