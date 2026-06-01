"""
pipeline/runs.py – CRUD endpoints for pipeline run management.

Endpoints:
    POST   /pipeline/run          – upload document + start V2 run
    POST   /pipeline/runs         – [V3] start DAG pipeline run from template
    GET    /pipeline/runs         – paginated list of runs
    GET    /pipeline/runs/{run_id} – get one run (with results)
    DELETE /pipeline/runs/{run_id} – delete run + files
"""

from __future__ import annotations

import json as _json
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
    status,
    UploadFile,
)

from app.api.v1.deps import get_current_user, require_admin, require_not_dev

from app.config import settings
from app.db import crud
from app.schemas.pipeline import (
    DeriveRunRequest,
    NodeCompareResponse,
    NodeCompareItem,
    PipelineResultResponse,
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
    _: object = Depends(require_not_dev),
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
    _: object = Depends(require_not_dev),
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

    try:
        parsed_run_params: dict = _json.loads(run_params)
    except _json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"run_params is not valid JSON: {exc}",
        ) from exc

    template = await crud.get_pipeline_template(template_id)
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
        ) from exc

    if llm_profile_id is not None:
        profile = await crud.get_llm_profile(llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile '{llm_profile_id}' not found.",
            )

    _, running_count = await crud.get_all_pipeline_runs(
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

    run = await crud.create_dag_run(
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
    _: object = Depends(get_current_user),
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
        except ValueError as _exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid status filter '{status_filter}'. "
                    f"Valid values: {[s.value for s in PipelineStatus]}"
                ),
            ) from _exc

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
    _: object = Depends(get_current_user),
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
                node_id=r.node_id,
                output=r.output,
                created_at=r.created_at,
                llm_profile_id=r.llm_profile_id,
                is_inherited=r.is_inherited,
                source_run_id=r.source_run_id,
                duration_seconds=r.duration_seconds,
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
async def delete_pipeline_run(
    run_id: str,
    _: object = Depends(require_admin),
) -> None:
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
        except Exception as exc:  # pylint: disable=broad-exception-caught
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
# POST /pipeline/runs/{run_id}/derive  (derived / checkpoint run)
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/runs/{run_id}/derive",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Derive a new run from a checkpoint",
    description=(
        "Creates a new pipeline run derived from an existing completed run. "
        "All nodes *upstream* of ``rerun_from_node`` are inherited (outputs copied "
        "from the parent) so only ``rerun_from_node`` and its downstream nodes are "
        "re-executed. Optionally override the LLM profile globally or per-node.\n\n"
        "This is the recommended way to A/B-test LLM changes or re-run a single "
        "pipeline layer without paying the full execution cost."
    ),
)
async def derive_pipeline_run(
    run_id: str,
    body: DeriveRunRequest,
    background_tasks: BackgroundTasks,
    _: object = Depends(require_not_dev),
) -> PipelineRunResponse:
    """Create a derived run from an existing checkpoint."""
    parent = await _get_run_or_404(run_id)

    if parent.template_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Derive is only supported for V3 template-based runs.",
        )

    # Verify the parent run is completed or failed (not still running)
    if parent.status not in (
        "completed",
        "failed",
        "cancelled",
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot derive from a run with status '{parent.status}'. "
                "Parent run must be completed, failed, or cancelled."
            ),
        )

    # Verify rerun_from_node exists in the parent template snapshot
    snapshot_nodes = {
        n["node_id"]
        for n in (parent.template_snapshot or {}).get("nodes", [])
    }
    if snapshot_nodes and body.rerun_from_node not in snapshot_nodes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Node '{body.rerun_from_node}' not found in parent run's template snapshot. "
                f"Available nodes: {sorted(snapshot_nodes)}"
            ),
        )

    # Validate overridden LLM profiles exist
    effective_llm = body.llm_profile_id or parent.llm_profile_id
    if effective_llm is not None:
        profile = await crud.get_llm_profile(effective_llm)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile '{effective_llm}' not found.",
            )
    for nid, pid in body.node_llm_overrides.items():
        profile = await crud.get_llm_profile(pid)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM profile '{pid}' not found (node_llm_overrides['{nid}']).",
            )

    # Validate node_input_overrides keys exist in template snapshot
    if body.node_input_overrides and snapshot_nodes:
        invalid_override_nodes = set(body.node_input_overrides.keys()) - snapshot_nodes
        if invalid_override_nodes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"node_input_overrides references unknown node(s): "
                    f"{sorted(invalid_override_nodes)}. "
                    f"Available nodes: {sorted(snapshot_nodes)}"
                ),
            )

    new_run_id = str(uuid.uuid4())
    run_params = {**parent.run_params}
    if body.label:
        run_params["label"] = body.label

    new_run = await crud.create_dag_run(
        run_id=new_run_id,
        template_id=parent.template_id,
        template_snapshot=parent.template_snapshot or {},
        document_name=parent.document_name,
        file_path=parent.file_path or parent.document_path,
        llm_profile_id=effective_llm,
        run_params=run_params,
        parent_run_id=run_id,
        rerun_from_node=body.rerun_from_node,
        node_llm_overrides=body.node_llm_overrides,
        node_input_overrides=body.node_input_overrides,
    )

    logger.info(
        "[Pipeline] Derived run  new_run_id=%r  parent=%r  from_node=%r",
        new_run_id,
        run_id,
        body.rerun_from_node,
    )

    background_tasks.add_task(
        _run_dag_pipeline_background,
        run_id=new_run_id,
        template_id=parent.template_id,
        file_path=parent.file_path or parent.document_path,
        document_name=parent.document_name,
        llm_profile_id=effective_llm,
        run_params=run_params,
        parent_run_id=run_id,
        rerun_from_node=body.rerun_from_node,
        node_llm_overrides=body.node_llm_overrides,
        node_input_overrides=body.node_input_overrides,
    )

    return await _dag_run_to_response(new_run)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/compare
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/compare",
    response_model=NodeCompareResponse,
    summary="Compare a node's output across multiple runs",
    description=(
        "Returns the output of the same DAG node from two or more runs side by "
        "side, enabling A/B comparisons between different LLM configs or "
        "re-executions. Pass ``run_ids`` as a comma-separated list."
    ),
)
async def compare_runs(
    node_id: Annotated[str, Query(description="DAG node ID to compare")],
    run_ids: Annotated[
        str,
        Query(description="Comma-separated list of run IDs to compare (min 2)"),
    ],
    _: object = Depends(get_current_user),
) -> NodeCompareResponse:
    """Compare one node's output across multiple runs."""
    ids = [r.strip() for r in run_ids.split(",") if r.strip()]
    if len(ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least 2 run IDs are required for comparison.",
        )

    items: list[NodeCompareItem] = []
    for rid in ids:
        result = await crud.get_node_result(rid, node_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No result found for node '{node_id}' in run '{rid}'.",
            )
        items.append(
            NodeCompareItem(
                run_id=rid,
                output=result.output,
                duration_seconds=result.duration_seconds,
                llm_profile_id=result.llm_profile_id,
                is_inherited=result.is_inherited,
                created_at=result.created_at,
            )
        )

    return NodeCompareResponse(node_id=node_id, runs=items)


# ─────────────────────────────────────────────────────────────────────────────
# GET /pipeline/runs/{run_id}/nodes/{node_id}/export
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/nodes/{node_id}/export",
    summary="Export a node's output as a JSON file download",
    description=(
        "Returns the raw output of a specific DAG node as a downloadable JSON "
        "file. Useful for inspecting, archiving, or replaying individual pipeline "
        "layer outputs without having to copy from the run detail page."
    ),
)
async def export_node_output(
    run_id: str,
    node_id: str,
    _: object = Depends(get_current_user),
) -> Any:
    """Download the output of a single node as a JSON file."""
    from fastapi.responses import JSONResponse

    await _get_run_or_404(run_id)  # 404 if run doesn't exist
    result = await crud.get_node_result(run_id, node_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No result found for node '{node_id}' in run '{run_id}'.",
        )

    filename = f"{run_id[:8]}_{node_id}_output.json"
    return JSONResponse(
        content=result.output,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
