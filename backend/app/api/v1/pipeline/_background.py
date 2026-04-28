"""
pipeline/_background.py – Background task functions for pipeline execution.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.db import crud
from app.schemas.pipeline import PipelineStatus

logger = logging.getLogger(__name__)


async def _run_pipeline_background(
    run_id: str,
    file_path: str,
    document_name: str,
    llm_profile_id: Optional[str],
    skip_execution: bool,
    environment: str,
) -> None:
    """Async background task that drives the V2 full pipeline for one run."""
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

    current_loop = asyncio.get_running_loop()
    manager.set_loop(current_loop)

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
            mock_mode=None,
            environment=environment,
            skip_execution=skip_execution,
        )

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

    except Exception as exc:  # pylint: disable=broad-exception-caught
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


async def _run_dag_pipeline_background(
    run_id: str,
    template_id: str,
    file_path: Optional[str],
    document_name: str,
    llm_profile_id: Optional[str],
    run_params: dict,
) -> None:
    """Background task for the V3 DAG pipeline runner."""
    import json
    from datetime import datetime, timezone

    from app.api.v1.websocket import manager
    from app.core.dag_pipeline_runner import DAGPipelineRunner
    from app.core.dag_resolver import DAGValidationError

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

        initial_input: dict = {
            "file_path": file_path,
            "document_name": document_name,
            **run_params,
        }

        if file_path:
            try:
                from app.tools.document_parser import parse_document

                document_content = parse_document(file_path)
                initial_input["document_content"] = document_content
                logger.info(
                    "[V3-Pipeline] Parsed document %r: %d chars",
                    document_name,
                    len(document_content),
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "[V3-Pipeline] Could not parse document %r: %s",
                    file_path,
                    exc,
                )

        await runner.run(initial_input)

    except DAGValidationError as exc:
        logger.error("[V3-Pipeline] DAG validation error  run_id=%r: %s", run_id, exc)
        await crud.update_pipeline_run(run_id, status="failed", error_message=str(exc))
        ws_broadcaster("run.failed", {"error": str(exc)})

    except Exception as exc:  # pylint: disable=broad-exception-caught
        error_detail = str(exc)
        logger.exception(
            "[V3-Pipeline] Unhandled error  run_id=%r  error=%s", run_id, error_detail
        )
        await crud.update_pipeline_run(
            run_id, status="failed", error_message=error_detail
        )
        ws_broadcaster("run.failed", {"error": error_detail})
