"""
pipeline/_background.py – Background task functions for pipeline execution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.config import settings
from app.db import crud

logger = logging.getLogger(__name__)


async def _run_dag_pipeline_background(
    run_id: str,
    template_id: str,
    file_path: Optional[str],
    document_name: str,
    llm_profile_id: Optional[str],
    run_params: dict,
    parent_run_id: Optional[str] = None,
    rerun_from_node: Optional[str] = None,
    node_llm_overrides: Optional[dict] = None,
    node_input_overrides: Optional[dict] = None,
) -> None:
    """Background task for the V3 DAG pipeline runner."""
    import json
    from datetime import datetime, timezone

    from app.api.v1.websocket import manager
    from app.core.dag_pipeline_runner import DAGPipelineRunner
    from app.core.dag_resolver import DAGValidationError

    logger.info(
        "[V3-Pipeline] Background task started  run_id=%r  template=%r  parent=%r",
        run_id,
        template_id,
        parent_run_id,
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
            mock_mode=settings.MOCK_CREWS,
            parent_run_id=parent_run_id,
            rerun_from_node=rerun_from_node,
            node_llm_overrides=node_llm_overrides,
            node_input_overrides=node_input_overrides,
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
