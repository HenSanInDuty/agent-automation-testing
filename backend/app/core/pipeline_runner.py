from __future__ import annotations

"""
core/pipeline_runner.py
───────────────────────
V2 async pipeline orchestrator — reads stage configs dynamically from MongoDB
and supports pause / resume / cancel via SignalManager.

Pipeline flow (dynamic — driven by StageConfigDocument records):
    [Document file]
        → stage_1  (e.g. ingestion)   → output_1
        → stage_2  (e.g. testcase)    → output_2
        → stage_3  (e.g. execution)   → output_3
        → stage_4  (e.g. reporting)   → output_4
        → … any custom stages …

Responsibilities:
  - Load enabled stages from MongoDB at run-time (order ascending).
  - Create / update the PipelineRunDocument at each stage boundary.
  - Persist intermediate results via crud.save_pipeline_result.
  - Emit structured WebSocket events via an optional sync callback.
  - Check SignalManager between stages for pause / resume / cancel.
  - Respect per-stage timeouts from StageConfigDocument.timeout_seconds.
  - Support MOCK_CREWS mode for testing without a live LLM.

Usage::

    from app.core.pipeline_runner import run_pipeline_async

    result = await run_pipeline_async(
        run_id="abc-123",
        file_path="/uploads/spec.pdf",
        document_name="spec.pdf",
        ws_broadcaster=my_broadcaster,
    )

Signal handling::

    from app.core.signal_manager import signal_manager, PipelineSignal

    # Pause a running pipeline (checked before the next stage starts):
    await signal_manager.set_signal(run_id, PipelineSignal.PAUSE)

    # Resume after pause:
    await signal_manager.set_signal(run_id, PipelineSignal.RESUME)

    # Cancel (acts immediately on next stage boundary):
    await signal_manager.set_signal(run_id, PipelineSignal.CANCEL)
"""

import asyncio
import importlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from app.config import settings
from app.db import crud

logger = logging.getLogger(__name__)

# Callback type: (event_type: str, data: dict) -> None
ProgressCallback = Callable[[str, dict[str, Any]], None]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# PipelineRunnerV2
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunnerV2:
    """
    V2 fully-async pipeline orchestrator.

    Reads stage configurations dynamically from MongoDB so that custom stages
    and reordering take effect without any code changes.  Supports
    pause / resume / cancel via the module-level :data:`signal_manager`
    singleton.

    Args:
        run_id:          UUID string of the PipelineRun record.
        run_profile_id:  Optional MongoDB ObjectId string for the run-level
                         LLM profile override.
        ws_broadcaster:  Optional sync callback for real-time event streaming.
                         Signature: ``(event_type: str, data: dict) -> None``.
        mock_mode:       When ``True``, all crews skip LLM calls and return
                         deterministic mock output.  Falls back to
                         ``settings.MOCK_CREWS`` when ``None``.
        environment:     Target test-environment name forwarded to the
                         execution crew.
    """

    def __init__(
        self,
        run_id: str,
        run_profile_id: Optional[str] = None,
        ws_broadcaster: Optional[Callable] = None,
        mock_mode: Optional[bool] = None,
        environment: str = "default",
    ) -> None:
        self._run_id = run_id
        self._run_profile_id = run_profile_id
        self._ws_broadcaster = ws_broadcaster
        self._environment = environment
        self._mock_mode: bool = (
            bool(getattr(settings, "MOCK_CREWS", False))
            if mock_mode is None
            else mock_mode
        )
        self._completed_stages: list[str] = []
        self._t_start: float = 0.0

        logger.info(
            "[PipelineRunnerV2] Initialised  run_id=%r  mock=%s  profile=%s  env=%s",
            run_id,
            self._mock_mode,
            run_profile_id,
            environment,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    async def run(
        self,
        file_path: str | Path,
        document_name: Optional[str] = None,
        skip_execution: bool = False,
    ) -> dict[str, Any]:
        """Execute the full pipeline end-to-end.

        Loads all enabled stages from MongoDB (ordered by ``order`` ascending),
        optionally skips execution and reporting, then iterates through stages.
        Between each stage the runner checks the :data:`signal_manager` for
        PAUSE / CANCEL signals and reacts accordingly.

        Args:
            file_path:      Path to the requirements document on disk.
            document_name:  Optional display name (defaults to filename).
            skip_execution: When ``True``, execution and reporting stages are
                            excluded from this run.

        Returns:
            A dict with keys ``run_id``, ``status``, ``completed_stages``,
            ``error``, and ``duration_seconds``.
        """
        from app.core.signal_manager import PipelineSignal, signal_manager

        file_path = Path(file_path)
        doc_name = document_name or file_path.name
        self._t_start = time.monotonic()

        # ── Load enabled stages ───────────────────────────────────────────
        stages = await crud.get_all_stage_configs(enabled_only=True)

        if skip_execution:
            stages = [s for s in stages if s.stage_id not in ("execution", "reporting")]

        if not stages:
            raise ValueError("No enabled stages found in database")

        # ── Signal run.started ────────────────────────────────────────────
        self._emit(
            "run.started",
            {
                "document_name": doc_name,
                "total_stages": len(stages),
                "mock_mode": self._mock_mode,
            },
        )
        await crud.update_pipeline_status(self._run_id, "running", started_at=_now())

        # Stage-to-stage data propagation
        stage_input: dict[str, Any] = {
            "file_path": str(file_path),
            "document_name": doc_name,
        }
        error: Optional[str] = None

        try:
            for stage_config in stages:
                # ── Check signal before each stage ────────────────────────
                signal = await signal_manager.get_signal(self._run_id)

                if signal == PipelineSignal.CANCEL:
                    await self._handle_cancel()
                    return self._build_result("cancelled", error="Cancelled by user")

                elif signal == PipelineSignal.PAUSE:
                    await self._handle_pause(stage_config.stage_id)
                    # Block until RESUME or CANCEL (or timeout → auto-cancel)
                    signal = await signal_manager.wait_for_resume(self._run_id)
                    if signal == PipelineSignal.CANCEL:
                        await self._handle_cancel()
                        return self._build_result(
                            "cancelled",
                            error="Cancelled by user after pause",
                        )
                    # RESUME received — continue running
                    await crud.update_pipeline_status(
                        self._run_id,
                        "running",
                        resumed_at=_now(),
                    )
                    self._emit(
                        "run.resumed",
                        {
                            "message": "Pipeline resumed by user",
                            "continuing_from": stage_config.stage_id,
                        },
                    )
                    await signal_manager.clear_signal(self._run_id)

                # ── Execute stage ─────────────────────────────────────────
                logger.info(
                    "[PipelineRunnerV2][%s] Starting stage %r",
                    self._run_id[:8],
                    stage_config.stage_id,
                )
                self._emit("stage.started", {"stage": stage_config.stage_id})
                await crud.update_pipeline_status(
                    self._run_id,
                    "running",
                    current_stage=stage_config.stage_id,
                )

                try:
                    stage_output = await self._execute_stage(stage_config, stage_input)

                    await crud.save_pipeline_result(
                        self._run_id,
                        stage_config.stage_id,
                        "crew_output",
                        stage_output,
                    )

                    self._completed_stages.append(stage_config.stage_id)
                    await crud.update_pipeline_status(
                        self._run_id,
                        "running",
                        completed_stages=self._completed_stages,
                    )

                    self._emit(
                        "stage.completed",
                        {
                            "stage": stage_config.stage_id,
                            "has_full_results": True,
                        },
                    )

                    logger.info(
                        "[PipelineRunnerV2][%s] Stage %r completed",
                        self._run_id[:8],
                        stage_config.stage_id,
                    )

                    # Propagate output as next stage's input
                    stage_input = (
                        stage_output
                        if isinstance(stage_output, dict)
                        else {"output": stage_output}
                    )
                    # Always re-inject file context so every stage has access
                    stage_input["file_path"] = str(file_path)
                    stage_input["document_name"] = doc_name

                except asyncio.TimeoutError:
                    error = (
                        f"Stage '{stage_config.stage_id}' timed out after "
                        f"{stage_config.timeout_seconds}s"
                    )
                    self._emit(
                        "stage.failed",
                        {"stage": stage_config.stage_id, "error": error},
                    )
                    raise

                except Exception as exc:
                    error = str(exc)
                    self._emit(
                        "stage.failed",
                        {"stage": stage_config.stage_id, "error": error},
                    )
                    raise

        except Exception as exc:
            error = str(exc)
            logger.exception(
                "[PipelineRunnerV2][%s] Pipeline failed: %s",
                self._run_id[:8],
                error,
            )
            await crud.update_pipeline_status(
                self._run_id,
                "failed",
                error=error,
                completed_stages=self._completed_stages,
            )
            self._emit("run.failed", {"error": error})
            return self._build_result("failed", error=error)

        # ── Pipeline completed ────────────────────────────────────────────
        duration = time.monotonic() - self._t_start
        await crud.update_pipeline_status(
            self._run_id,
            "completed",
            completed_stages=self._completed_stages,
        )
        self._emit(
            "run.completed",
            {
                "total_stages": len(stages),
                "duration_seconds": round(duration, 2),
            },
        )
        logger.info(
            "[PipelineRunnerV2][%s] Pipeline completed in %.1fs  stages=%s",
            self._run_id[:8],
            duration,
            self._completed_stages,
        )
        return self._build_result("completed")

    # ─────────────────────────────────────────────────────────────────────────
    # Stage dispatch
    # ─────────────────────────────────────────────────────────────────────────

    async def _execute_stage(
        self,
        stage_config: Any,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a single stage to the appropriate crew.

        Resolution order:
        1. ``pure_python`` → look up builtin crew class; call ``run()``
           directly (supports both sync and async ``run`` methods).
        2. ``crewai_sequential`` / ``crewai_hierarchical`` → try builtin crew
           first (for the 4 default stages); fall back to
           :class:`~app.crews.dynamic_crew.DynamicCrewAICrew` for custom
           stages.

        Stage timeouts are enforced via :func:`asyncio.wait_for`.
        ``timeout_seconds == 0`` means no timeout.

        Args:
            stage_config: :class:`~app.db.models.StageConfigDocument` instance.
            input_data:   Dict of inputs passed from the previous stage.

        Returns:
            Dict output from the crew's ``run()`` method.

        Raises:
            asyncio.TimeoutError: When the stage exceeds its timeout budget.
            ValueError:           When ``crew_type`` is unknown.
        """
        timeout: Optional[float] = (
            float(stage_config.timeout_seconds)
            if stage_config.timeout_seconds > 0
            else None
        )

        if stage_config.crew_type == "pure_python":
            crew = self._get_builtin_crew(stage_config.stage_id)
            if asyncio.iscoroutinefunction(crew.run):
                coro = crew.run(input_data)
            else:
                coro = asyncio.to_thread(crew.run, input_data)
            return await asyncio.wait_for(coro, timeout=timeout)

        elif stage_config.crew_type in ("crewai_sequential", "crewai_hierarchical"):
            builtin_crew = self._try_get_builtin_crew(stage_config.stage_id)
            if builtin_crew is not None:
                coro = asyncio.to_thread(builtin_crew.run, input_data)
                return await asyncio.wait_for(coro, timeout=timeout)

            # Custom stage: build a DynamicCrewAICrew from DB agent configs
            agent_configs = await crud.get_agent_configs_for_stage(
                stage_config.stage_id, enabled_only=True
            )
            from app.crews.dynamic_crew import DynamicCrewAICrew

            process = (
                "sequential"
                if stage_config.crew_type == "crewai_sequential"
                else "hierarchical"
            )
            crew = DynamicCrewAICrew(
                stage=stage_config.stage_id,
                agent_configs=agent_configs,
                run_id=self._run_id,
                run_profile_id=self._run_profile_id,
                progress_callback=self._ws_broadcaster,
                mock_mode=self._mock_mode,
                process=process,
            )
            coro = asyncio.to_thread(crew.run, input_data)
            return await asyncio.wait_for(coro, timeout=timeout)

        else:
            raise ValueError(
                f"Unknown crew_type {stage_config.crew_type!r} "
                f"for stage {stage_config.stage_id!r}"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Builtin crew registry
    # ─────────────────────────────────────────────────────────────────────────

    #: Mapping of stage_id → (module_path, class_name) for the 4 builtin crews.
    _BUILTIN_CREWS: dict[str, tuple[str, str]] = {
        "ingestion": ("app.crews.ingestion_crew", "IngestionCrew"),
        "testcase": ("app.crews.testcase_crew", "TestcaseCrew"),
        "execution": ("app.crews.execution_crew", "ExecutionCrew"),
        "reporting": ("app.crews.reporting_crew", "ReportingCrew"),
    }

    def _get_builtin_crew(self, stage_id: str) -> Any:
        """Instantiate and return a builtin crew for *stage_id*.

        Args:
            stage_id: Pipeline stage slug (e.g. ``"ingestion"``).

        Returns:
            A crew instance with a ``run(input_data)`` method.

        Raises:
            ValueError:  When no builtin crew is registered for *stage_id*.
            ImportError: When the crew's module cannot be imported.
        """
        entry = self._BUILTIN_CREWS.get(stage_id)
        if not entry:
            raise ValueError(f"No builtin crew registered for stage: {stage_id!r}")

        module_path, class_name = entry
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls(
            run_id=self._run_id,
            run_profile_id=self._run_profile_id,
            progress_callback=self._ws_broadcaster,
            mock_mode=self._mock_mode,
        )

    def _try_get_builtin_crew(self, stage_id: str) -> Optional[Any]:
        """Try to get a builtin crew instance; return ``None`` if unavailable.

        This is used as a soft lookup — when a stage matches a builtin stage ID
        the registered crew is returned, otherwise ``None`` tells the caller to
        use a :class:`~app.crews.dynamic_crew.DynamicCrewAICrew` instead.

        Args:
            stage_id: Pipeline stage slug.

        Returns:
            A crew instance, or ``None`` if the stage is not a builtin.
        """
        try:
            return self._get_builtin_crew(stage_id)
        except (ValueError, ImportError, Exception):
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Signal handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_pause(self, next_stage_id: str) -> None:
        """Transition to ``paused`` status and emit ``run.paused`` event.

        Args:
            next_stage_id: The stage that will execute once the run resumes.
        """
        logger.info(
            "[PipelineRunnerV2][%s] Pausing before stage %r",
            self._run_id[:8],
            next_stage_id,
        )
        await crud.update_pipeline_status(
            self._run_id,
            "paused",
            paused_at=_now(),
            completed_stages=self._completed_stages,
        )
        self._emit(
            "run.paused",
            {
                "message": "Pipeline paused by user",
                "completed_stages": self._completed_stages,
                "next_stage": next_stage_id,
            },
        )

    async def _handle_cancel(self) -> None:
        """Transition to ``cancelled`` status, emit event and clean up signal."""
        from app.core.signal_manager import signal_manager

        logger.info(
            "[PipelineRunnerV2][%s] Cancelling pipeline",
            self._run_id[:8],
        )
        await crud.update_pipeline_status(
            self._run_id,
            "cancelled",
            error="Cancelled by user",
            completed_stages=self._completed_stages,
        )
        self._emit(
            "run.cancelled",
            {
                "message": "Pipeline cancelled by user",
                "completed_stages": self._completed_stages,
            },
        )
        await signal_manager.clear_signal(self._run_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Event emission
    # ─────────────────────────────────────────────────────────────────────────

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Forward a pipeline event to the registered WebSocket broadcaster.

        The ``run_id`` is automatically injected into *data*.  When no
        broadcaster is registered events are only logged at DEBUG level.

        Args:
            event_type: Dot-separated event name (e.g. ``"stage.completed"``).
            data:       Event payload dict.
        """
        payload: dict[str, Any] = {"run_id": self._run_id, **data}
        if self._ws_broadcaster is not None:
            try:
                self._ws_broadcaster(event_type, payload)
            except Exception as exc:
                logger.warning(
                    "[PipelineRunnerV2] Broadcaster raised an exception (event=%r): %s",
                    event_type,
                    exc,
                )
        else:
            logger.debug("[PipelineRunnerV2] event=%r  data=%r", event_type, payload)

    # ─────────────────────────────────────────────────────────────────────────
    # Result builder
    # ─────────────────────────────────────────────────────────────────────────

    def _build_result(self, status: str, error: Optional[str] = None) -> dict[str, Any]:
        """Build the standardised result dict returned by :meth:`run`.

        Args:
            status: Terminal pipeline status string (e.g. ``"completed"``).
            error:  Optional human-readable error message.

        Returns:
            Dict with ``run_id``, ``status``, ``completed_stages``,
            ``error``, and ``duration_seconds``.
        """
        return {
            "run_id": self._run_id,
            "status": status,
            "completed_stages": list(self._completed_stages),
            "error": error,
            "duration_seconds": round(time.monotonic() - self._t_start, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatibility alias
# ─────────────────────────────────────────────────────────────────────────────

#: Deprecated alias — use :class:`PipelineRunnerV2` directly.
PipelineRunner = PipelineRunnerV2


# ─────────────────────────────────────────────────────────────────────────────
# Async entry point (used by background task in api/v1/pipeline.py)
# ─────────────────────────────────────────────────────────────────────────────


async def run_pipeline_async(
    run_id: str,
    file_path: str | Path,
    document_name: Optional[str] = None,
    run_profile_id: Optional[str] = None,
    ws_broadcaster: Optional[Callable] = None,
    mock_mode: Optional[bool] = None,
    environment: str = "default",
    skip_execution: bool = False,
    # Legacy / ignored parameters kept for call-site backward compatibility:
    db: Any = None,
    execution_config: Optional[dict[str, Any]] = None,
    ingestion_options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Async entry point for the pipeline.

    Used by the background task in ``api/v1/pipeline.py``.  V2 implementation
    is fully async — no thread-pool executor needed.

    Args:
        run_id:           UUID of the pipeline run.
        file_path:        Path to the document to process.
        document_name:    Optional display name.
        run_profile_id:   Optional MongoDB ObjectId string of the LLM profile
                          override.
        ws_broadcaster:   Optional sync or async progress callback.  When an
                          async callable is supplied it is scheduled via
                          ``asyncio.ensure_future`` so the runner's synchronous
                          ``_emit`` path still works.
        mock_mode:        Force mock mode.  ``None`` honours ``MOCK_CREWS`` env.
        environment:      Target execution environment name.
        skip_execution:   Skip Execution + Reporting stages when ``True``.
        db:               **Ignored** — accepted for backward compatibility with
                          V1 call sites that passed an SQLAlchemy session.
        execution_config: **Ignored** — accepted for backward compatibility.
        ingestion_options: **Ignored** — accepted for backward compatibility.

    Returns:
        Dict with ``run_id``, ``status``, ``completed_stages``, ``error``,
        and ``duration_seconds``.
    """
    import inspect

    # Wrap an async broadcaster into a sync wrapper so PipelineRunnerV2._emit
    # can call it without awaiting (it schedules the coroutine on the loop).
    if ws_broadcaster is None:
        sync_broadcaster: Optional[Callable] = None
    elif inspect.iscoroutinefunction(ws_broadcaster):
        _async_ws = ws_broadcaster  # capture for closure

        def _sync_wrap(event_type: str, data: dict[str, Any]) -> None:
            asyncio.ensure_future(_async_ws(event_type, data))

        sync_broadcaster = _sync_wrap
    else:
        sync_broadcaster = ws_broadcaster

    runner = PipelineRunnerV2(
        run_id=run_id,
        run_profile_id=run_profile_id,
        ws_broadcaster=sync_broadcaster,
        mock_mode=mock_mode,
        environment=environment,
    )
    return await runner.run(
        file_path=file_path,
        document_name=document_name,
        skip_execution=skip_execution,
    )
