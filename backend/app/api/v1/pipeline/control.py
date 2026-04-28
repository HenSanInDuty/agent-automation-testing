"""
pipeline/control.py – Pause / resume / cancel endpoints for pipeline runs.

Endpoints:
    POST /pipeline/runs/{run_id}/pause   – pause a running pipeline
    POST /pipeline/runs/{run_id}/resume  – resume a paused pipeline
    POST /pipeline/runs/{run_id}/cancel  – request cancellation
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.db import crud
from app.schemas.pipeline import PipelineStatus

from ._helpers import PipelineActionResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/runs/{run_id}/pause",
    response_model=PipelineActionResponse,
    summary="Pause a running pipeline",
    description=(
        "Requests that the pipeline pause after its current stage completes. "
        "Only runs with ``status=running`` can be paused."
    ),
)
async def pause_pipeline(run_id: str) -> PipelineActionResponse:
    """Request that a running pipeline pause after the current stage."""
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
    """Request that a paused pipeline resume execution."""
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


@router.post(
    "/runs/{run_id}/cancel",
    response_model=PipelineActionResponse,
    summary="Cancel a running or paused pipeline",
    description=(
        "Requests cancellation of a pipeline that is currently ``running``, "
        "``paused``, or ``pending``.  Runs already in a terminal state cannot be "
        "cancelled."
    ),
)
async def cancel_pipeline(run_id: str) -> PipelineActionResponse:
    """Request cancellation of a running, paused, or pending pipeline."""
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
