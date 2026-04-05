from __future__ import annotations

"""
core/pipeline_runner.py
───────────────────────
Main pipeline orchestrator — coordinates all four crews in sequence.

Pipeline flow:
    [Document file]
        → IngestionCrew   → RequirementJSON     (saved to DB)
        → TestcaseCrew    → TestCaseJSON        (saved to DB)
        → ExecutionCrew   → ExecutionResultJSON (saved to DB)
        → ReportingCrew   → PipelineReport      (saved to DB)

Responsibilities:
  - Create / update the PipelineRun DB record at each stage boundary.
  - Persist intermediate results as PipelineResult rows for later retrieval.
  - Emit structured WebSocket events (via an optional async broadcaster).
  - Propagate errors from one stage without crashing the whole pipeline
    (e.g. if execution fails, we still run reporting with partial data).
  - Respect per-stage timeouts defined in settings.
  - Support MOCK_CREWS mode for testing without a live LLM.

Usage (synchronous, e.g. from a background task)::

    from app.core.pipeline_runner import PipelineRunner

    runner = PipelineRunner(db=session, run_id="abc-123")
    result = runner.run(file_path="/uploads/spec.pdf", document_name="spec.pdf")

Usage with WebSocket broadcaster::

    async def ws_broadcast(event_type: str, data: dict) -> None:
        await manager.broadcast(run_id, json.dumps({"event": event_type, **data}))

    runner = PipelineRunner(
        db=session,
        run_id="abc-123",
        run_profile_id=2,
        ws_broadcaster=ws_broadcast,
    )
    result = runner.run(file_path="/uploads/spec.pdf")
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import PipelineResult, PipelineRun
from app.schemas.pipeline_io import (
    ExecutionOutput,
    IngestionOutput,
    PipelineReport,
    TestCaseOutput,
)

logger = logging.getLogger(__name__)

# Callback type: (event_type: str, data: dict) -> None
# The callback may be synchronous or asynchronous (async variant handled in
# the async wrapper at the bottom of this module).
ProgressCallback = Callable[[str, dict[str, Any]], None]


# ─────────────────────────────────────────────────────────────────────────────
# PipelineRunner
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunner:
    """
    Synchronous pipeline orchestrator.

    Coordinates the four pipeline crews in sequence, persists intermediate
    results to the database, and emits WebSocket-compatible progress events
    via an optional callback.

    Args:
        db:               Active SQLAlchemy session (caller owns lifecycle).
        run_id:           UUID string of the PipelineRun record.
        run_profile_id:   Optional LLM profile override for all agents.
        ws_broadcaster:   Optional callback for real-time event streaming.
                          Signature: (event_type: str, data: dict) -> None.
        mock_mode:        When True, all crews skip LLM calls and return
                          deterministic mock output.  Falls back to
                          settings.MOCK_CREWS if None.
        environment:      Target test environment name for execution crew.
    """

    def __init__(
        self,
        db: Session,
        run_id: str,
        run_profile_id: Optional[int] = None,
        ws_broadcaster: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        environment: str = "default",
    ) -> None:
        self._db = db
        self._run_id = run_id
        self._run_profile_id = run_profile_id
        self._ws_broadcaster = ws_broadcaster
        self._environment = environment

        # Resolve mock_mode
        if mock_mode is None:
            self._mock_mode: bool = bool(getattr(settings, "MOCK_CREWS", False))
        else:
            self._mock_mode = mock_mode

        # Shared state accumulated across stages
        self._ingestion_output: Optional[dict[str, Any]] = None
        self._testcase_output: Optional[dict[str, Any]] = None
        self._execution_output: Optional[dict[str, Any]] = None
        self._report_output: Optional[dict[str, Any]] = None

        logger.info(
            "[PipelineRunner] Initialised run_id=%r mock=%s profile=%s env=%s",
            run_id,
            self._mock_mode,
            run_profile_id,
            environment,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(  # noqa: C901  (complexity is intentional — it's the main orchestration method)
        self,
        file_path: str | Path,
        document_name: Optional[str] = None,
        ingestion_options: Optional[dict[str, Any]] = None,
        execution_config: Optional[dict[str, Any]] = None,
        skip_execution: bool = False,
    ) -> dict[str, Any]:
        """
        Execute the full four-stage pipeline for a single document.

        Args:
            file_path:         Absolute or relative path to the uploaded document.
            document_name:     Human-readable filename (defaults to the path basename).
            ingestion_options: Optional overrides for the IngestionCrew
                               (chunk_size, chunk_overlap, mock_mode).
            execution_config:  Optional overrides for the ExecutionCrew
                               (timeouts, execution_mode).
            skip_execution:    If True, skip the Execution and Reporting stages.
                               Useful when you only want test case generation.

        Returns:
            A dict with keys:
                run_id, document_name, status,
                ingestion, testcase, execution, report,
                started_at, finished_at, duration_seconds, error.

        Raises:
            FileNotFoundError: If the document file does not exist.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(
                "[Runner][%s] Document file not found: %r",
                self._run_id[:8],
                str(file_path),
            )
            raise FileNotFoundError(f"Document not found: {file_path}")

        doc_name = document_name or file_path.name
        t_start = time.monotonic()

        logger.info(
            "[Runner][%s] ════ PIPELINE START  doc=%r  profile=%s  mock=%s  skip_exec=%s  ws=%s",
            self._run_id[:8],
            doc_name,
            self._run_profile_id,
            self._mock_mode,
            skip_execution,
            "yes" if self._ws_broadcaster else "NO ← events will not be sent",
        )

        # Mark run as running
        self._update_db_status("running")
        self._emit(
            "run.started",
            {
                "document_name": doc_name,
                "total_agents": 18,
                "mock_mode": self._mock_mode,
            },
        )

        error: Optional[str] = None

        try:
            # ── Stage 1: Ingestion ────────────────────────────────────────────
            self._emit("stage.started", {"stage": "ingestion", "agent_count": 0})
            try:
                self._ingestion_output = self._run_ingestion(
                    file_path=file_path,
                    document_name=doc_name,
                    options=ingestion_options or {},
                )
                req_count = len((self._ingestion_output or {}).get("requirements", []))
                self._save_result(
                    "ingestion", "ingestion_pipeline", self._ingestion_output
                )
                self._emit(
                    "stage.completed",
                    {
                        "stage": "ingestion",
                        "requirements_count": req_count,
                    },
                )
                logger.info(
                    "[PipelineRunner][%s] Ingestion done: %d requirements",
                    self._run_id,
                    req_count,
                )
            except Exception as exc:
                error = f"Ingestion stage failed: {exc}"
                logger.exception(
                    "[Runner][%s] ── INGESTION FAILED (aborting pipeline): %s",
                    self._run_id[:8],
                    exc,
                )
                self._emit("log", {"message": error, "level": "error"})
                # Cannot continue without requirements
                self._update_db_status("failed", error=error)
                self._emit("run.failed", {"error": error})
                return self._build_result(doc_name, "failed", t_start, error=error)

            # ── Stage 2: Test Case Generation ─────────────────────────────────
            self._emit("stage.started", {"stage": "testcase", "agent_count": 10})
            try:
                self._testcase_output = self._run_testcase(
                    requirements=self._ingestion_output.get("requirements", []),
                    document_name=doc_name,
                )
                tc_count = len((self._testcase_output or {}).get("test_cases", []))
                self._save_result("testcase", "testcase_crew", self._testcase_output)
                self._emit(
                    "stage.completed",
                    {
                        "stage": "testcase",
                        "test_cases_count": tc_count,
                    },
                )
                logger.info(
                    "[PipelineRunner][%s] Testcase done: %d test cases",
                    self._run_id,
                    tc_count,
                )
            except Exception as exc:
                error = f"Test case generation failed: {exc}"
                logger.exception(
                    "[Runner][%s] ── TESTCASE FAILED (continuing with empty test cases): %s",
                    self._run_id[:8],
                    exc,
                )
                self._emit("log", {"message": error, "level": "error"})
                self._testcase_output = {"test_cases": [], "error": str(exc)}
                # Continue to reporting with partial data
                self._save_result("testcase", "testcase_crew", self._testcase_output)

            if skip_execution:
                logger.info(
                    "[PipelineRunner][%s] skip_execution=True — stopping after testcase stage.",
                    self._run_id,
                )
                duration = time.monotonic() - t_start
                self._update_db_status("completed")
                self._emit(
                    "run.completed",
                    {
                        "total_agents": 10,
                        "duration_seconds": round(duration, 2),
                    },
                )
                return self._build_result(doc_name, "completed", t_start)

            # ── Stage 3: Execution ────────────────────────────────────────────
            test_cases = (self._testcase_output or {}).get("test_cases", [])
            self._emit("stage.started", {"stage": "execution", "agent_count": 5})
            try:
                self._execution_output = self._run_execution(
                    test_cases=test_cases,
                    environment=self._environment,
                    execution_config=execution_config or {},
                )
                result_count = len((self._execution_output or {}).get("results", []))
                self._save_result("execution", "execution_crew", self._execution_output)
                exec_summary = (self._execution_output or {}).get("summary", {})
                self._emit(
                    "stage.completed",
                    {
                        "stage": "execution",
                        "results_count": result_count,
                        "pass_rate": exec_summary.get("pass_rate", 0.0),
                    },
                )
                logger.info(
                    "[PipelineRunner][%s] Execution done: %d results, %.1f%% pass rate",
                    self._run_id,
                    result_count,
                    exec_summary.get("pass_rate", 0.0),
                )
            except Exception as exc:
                error = f"Execution stage failed: {exc}"
                logger.exception(
                    "[Runner][%s] ── EXECUTION FAILED (continuing with empty results): %s",
                    self._run_id[:8],
                    exc,
                )
                self._emit("log", {"message": error, "level": "error"})
                # Build minimal error output so reporting can still run
                self._execution_output = {
                    "results": [],
                    "summary": {
                        "total": len(test_cases),
                        "passed": 0,
                        "failed": 0,
                        "skipped": 0,
                        "errors": len(test_cases),
                        "pass_rate": 0.0,
                        "duration_seconds": 0.0,
                    },
                    "environment": self._environment,
                    "execution_notes": [f"Execution crew failed: {exc}"],
                }
                self._save_result("execution", "execution_crew", self._execution_output)

            # ── Stage 4: Reporting ────────────────────────────────────────────
            exec_results = (self._execution_output or {}).get("results", [])
            exec_summary = (self._execution_output or {}).get("summary", {})
            requirements = (self._ingestion_output or {}).get("requirements", [])

            self._emit("stage.started", {"stage": "reporting", "agent_count": 3})
            try:
                self._report_output = self._run_reporting(
                    test_cases=test_cases,
                    exec_results=exec_results,
                    requirements=requirements,
                    exec_summary=exec_summary,
                    document_name=doc_name,
                )
                self._save_result("reporting", "reporting_crew", self._report_output)
                self._emit(
                    "stage.completed",
                    {
                        "stage": "reporting",
                        "coverage_percentage": (self._report_output or {}).get(
                            "coverage_percentage", 0.0
                        ),
                    },
                )
                logger.info(
                    "[PipelineRunner][%s] Reporting done: coverage=%.1f%%",
                    self._run_id,
                    (self._report_output or {}).get("coverage_percentage", 0.0),
                )
            except Exception as exc:
                report_error = f"Reporting stage failed: {exc}"
                logger.exception(
                    "[Runner][%s] ── REPORTING FAILED (pipeline still marked completed): %s",
                    self._run_id[:8],
                    exc,
                )
                self._emit("log", {"message": report_error, "level": "error"})
                # Build minimal report
                self._report_output = {
                    "coverage_percentage": 0.0,
                    "executive_summary": f"Reporting failed: {exc}",
                    "recommendations": [],
                    "risk_items": [f"Reporting crew error: {exc}"],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_test_cases": len(test_cases),
                    "pass_rate": exec_summary.get("pass_rate", 0.0),
                    "metrics": exec_summary,
                }
                self._save_result("reporting", "reporting_crew", self._report_output)
                # Reporting failure is non-fatal — pipeline is still "completed"

        except Exception as exc:
            # Unexpected top-level error (should rarely happen — each stage has its own try/except)
            error = f"Pipeline runner unexpected error: {exc}"
            logger.exception(
                "[Runner][%s] ════ PIPELINE UNEXPECTED FAILURE: %s",
                self._run_id[:8],
                exc,
            )
            self._update_db_status("failed", error=error)
            self._emit("run.failed", {"error": error})
            return self._build_result(doc_name, "failed", t_start, error=error)

        # ── Success ───────────────────────────────────────────────────────────
        duration = time.monotonic() - t_start
        self._update_db_status("completed")
        self._emit(
            "run.completed",
            {
                "total_agents": 18,
                "duration_seconds": round(duration, 2),
                "result_url": f"/api/v1/pipeline/runs/{self._run_id}",
            },
        )
        logger.info(
            "[Runner][%s] ════ PIPELINE COMPLETED  duration=%.1fs  "
            "requirements=%d  test_cases=%d  pass_rate=%s%%",
            self._run_id[:8],
            duration,
            len((self._ingestion_output or {}).get("requirements", [])),
            len((self._testcase_output or {}).get("test_cases", [])),
            (self._execution_output or {}).get("summary", {}).get("pass_rate", "n/a"),
        )

        return self._build_result(doc_name, "completed", t_start)

    # ─────────────────────────────────────────────────────────────────────────
    # Stage runners
    # ─────────────────────────────────────────────────────────────────────────

    def _run_ingestion(
        self,
        file_path: Path,
        document_name: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run IngestionCrew and return the output dict.

        Args:
            file_path:     Document file path.
            document_name: Display name.
            options:       Optional overrides (chunk_size, chunk_overlap, mock_mode).

        Returns:
            IngestionOutput.model_dump() dict.
        """
        t0 = time.monotonic()
        logger.info(
            "[Runner][%s] ── INGESTION START  file=%r  mock=%s  chunk_size=%s  chunk_overlap=%s",
            self._run_id[:8],
            str(file_path),
            options.get("mock_mode", self._mock_mode),
            options.get("chunk_size", settings.INGESTION_CHUNK_SIZE),
            options.get("chunk_overlap", settings.INGESTION_CHUNK_OVERLAP),
        )

        try:
            from app.crews.ingestion_crew import IngestionCrew

            crew = IngestionCrew(
                db=self._db,
                run_id=self._run_id,
                run_profile_id=self._run_profile_id,
                progress_callback=self._progress_callback,
                chunk_size=int(
                    options.get("chunk_size", settings.INGESTION_CHUNK_SIZE)
                ),
                chunk_overlap=int(
                    options.get("chunk_overlap", settings.INGESTION_CHUNK_OVERLAP)
                ),
            )

            input_data: dict[str, Any] = {
                "file_path": str(file_path),
                "document_name": document_name,
                "mock_mode": options.get("mock_mode", self._mock_mode),
            }
            if "chunk_size" in options:
                input_data["chunk_size"] = options["chunk_size"]
            if "chunk_overlap" in options:
                input_data["chunk_overlap"] = options["chunk_overlap"]

            result = crew.run(input_data)

            req_count = len(result.get("requirements", []))
            logger.info(
                "[Runner][%s] ── INGESTION DONE  elapsed=%.2fs  requirements=%d",
                self._run_id[:8],
                time.monotonic() - t0,
                req_count,
            )
            return result

        except Exception:
            logger.exception(
                "[Runner][%s] ── INGESTION FAILED  elapsed=%.2fs",
                self._run_id[:8],
                time.monotonic() - t0,
            )
            raise

    def _run_testcase(
        self,
        requirements: list[dict[str, Any]],
        document_name: str,
    ) -> dict[str, Any]:
        """
        Run TestcaseCrew and return the output dict.

        Args:
            requirements:  List of RequirementItem dicts from ingestion.
            document_name: Source document name.

        Returns:
            TestCaseOutput.model_dump() dict.
        """
        t0 = time.monotonic()
        logger.info(
            "[Runner][%s] ── TESTCASE START  requirements=%d  mock=%s",
            self._run_id[:8],
            len(requirements),
            self._mock_mode,
        )

        try:
            from app.crews.testcase_crew import TestcaseCrew

            crew = TestcaseCrew(
                db=self._db,
                run_id=self._run_id,
                run_profile_id=self._run_profile_id,
                progress_callback=self._progress_callback,
                mock_mode=self._mock_mode,
            )

            result = crew.run(
                {
                    "requirements": requirements,
                    "document_name": document_name,
                }
            )

            tc_count = len(result.get("test_cases", []))
            logger.info(
                "[Runner][%s] ── TESTCASE DONE  elapsed=%.2fs  test_cases=%d",
                self._run_id[:8],
                time.monotonic() - t0,
                tc_count,
            )
            return result

        except Exception:
            logger.exception(
                "[Runner][%s] ── TESTCASE FAILED  elapsed=%.2fs",
                self._run_id[:8],
                time.monotonic() - t0,
            )
            raise

    def _run_execution(
        self,
        test_cases: list[dict[str, Any]],
        environment: str,
        execution_config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run ExecutionCrew and return the output dict.

        Args:
            test_cases:       List of TestCase dicts from testcase crew.
            environment:      Target environment name.
            execution_config: Execution configuration overrides.

        Returns:
            ExecutionOutput.model_dump() dict.
        """
        t0 = time.monotonic()
        logger.info(
            "[Runner][%s] ── EXECUTION START  test_cases=%d  env=%r  mock=%s",
            self._run_id[:8],
            len(test_cases),
            environment,
            self._mock_mode,
        )

        try:
            from app.crews.execution_crew import ExecutionCrew

            crew = ExecutionCrew(
                db=self._db,
                run_id=self._run_id,
                run_profile_id=self._run_profile_id,
                progress_callback=self._progress_callback,
                mock_mode=self._mock_mode,
                environment=environment,
            )

            result = crew.run(
                {
                    "test_cases": test_cases,
                    "environment": environment,
                    "execution_config": execution_config,
                }
            )

            summary = result.get("summary", {})
            logger.info(
                "[Runner][%s] ── EXECUTION DONE  elapsed=%.2fs  total=%s  passed=%s  pass_rate=%s%%",
                self._run_id[:8],
                time.monotonic() - t0,
                summary.get("total", "?"),
                summary.get("passed", "?"),
                summary.get("pass_rate", "?"),
            )
            return result

        except Exception:
            logger.exception(
                "[Runner][%s] ── EXECUTION FAILED  elapsed=%.2fs",
                self._run_id[:8],
                time.monotonic() - t0,
            )
            raise

    def _run_reporting(
        self,
        test_cases: list[dict[str, Any]],
        exec_results: list[dict[str, Any]],
        requirements: list[dict[str, Any]],
        exec_summary: dict[str, Any],
        document_name: str,
    ) -> dict[str, Any]:
        """
        Run ReportingCrew and return the output dict.

        Args:
            test_cases:    List of TestCase dicts from testcase crew.
            exec_results:  List of TestExecutionResult dicts from execution crew.
            requirements:  List of RequirementItem dicts from ingestion.
            exec_summary:  ExecutionSummary dict (pass rate, totals, etc.).
            document_name: Source document display name.

        Returns:
            PipelineReport-compatible dict.
        """
        t0 = time.monotonic()
        logger.info(
            "[Runner][%s] ── REPORTING START  test_cases=%d  exec_results=%d  pass_rate=%s%%",
            self._run_id[:8],
            len(test_cases),
            len(exec_results),
            exec_summary.get("pass_rate", "?"),
        )

        try:
            from app.crews.reporting_crew import ReportingCrew

            crew = ReportingCrew(
                db=self._db,
                run_id=self._run_id,
                run_profile_id=self._run_profile_id,
                progress_callback=self._progress_callback,
                mock_mode=self._mock_mode,
            )

            result = crew.run(
                {
                    "test_cases_json": test_cases,
                    "execution_results_json": exec_results,
                    "requirements_json": requirements,
                    "execution_summary": exec_summary,
                    "document_name": document_name,
                }
            )

            logger.info(
                "[Runner][%s] ── REPORTING DONE  elapsed=%.2fs  coverage=%.1f%%",
                self._run_id[:8],
                time.monotonic() - t0,
                result.get("coverage_percentage", 0.0),
            )
            return result

        except Exception:
            logger.exception(
                "[Runner][%s] ── REPORTING FAILED  elapsed=%.2fs",
                self._run_id[:8],
                time.monotonic() - t0,
            )
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # Progress event emission
    # ─────────────────────────────────────────────────────────────────────────

    def _progress_callback(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Internal progress callback passed to each crew.

        Relays all crew events to the WebSocket broadcaster (if configured)
        and logs them.  Also handles ``agent.started`` and
        ``agent.completed`` events to update the DB agent_statuses field.

        Args:
            event_type: Dot-separated event name (e.g. "agent.started").
            data:       Event payload dict (always includes run_id).
        """
        _info_cb_events = {"agent.started", "agent.completed", "agent.failed"}
        if event_type in _info_cb_events:
            agent_id = data.get("agent_id", "?")
            extra = data.get("error", data.get("output_preview", ""))
            logger.info(
                "[Runner][%s] %-18s  agent=%-35s  %s",
                self._run_id[:8],
                event_type,
                agent_id,
                f"error={extra!r}"
                if event_type == "agent.failed"
                else (f"preview={str(extra)[:80]!r}" if extra else ""),
            )
        else:
            logger.debug(
                "[Runner][%s] callback event=%r  data_keys=%s",
                self._run_id[:8],
                event_type,
                sorted(data.keys()),
            )

        # Update per-agent DB status
        if event_type == "agent.started":
            agent_id = data.get("agent_id")
            if agent_id:
                self._update_agent_status(agent_id, "running")

        elif event_type == "agent.completed":
            agent_id = data.get("agent_id")
            if agent_id:
                self._update_agent_status(agent_id, "done")

        elif event_type == "agent.failed":
            agent_id = data.get("agent_id")
            if agent_id:
                self._update_agent_status(agent_id, "error")

        # Relay to WebSocket broadcaster
        self._emit(event_type, data)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Relay an event to the WebSocket broadcaster (if set).

        Always safe to call — silently ignores broadcaster errors so a WS
        failure never aborts the pipeline.

        Args:
            event_type: Event name string.
            data:       Event payload dict.
        """
        # Log important lifecycle events at INFO, everything else at DEBUG
        _info_events = {
            "run.started",
            "run.completed",
            "run.failed",
            "stage.started",
            "stage.completed",
        }
        if event_type in _info_events:
            logger.info(
                "[Runner][%s] EMIT %-20s  data=%s",
                self._run_id[:8],
                event_type,
                {k: v for k, v in data.items() if k not in ("run_id", "timestamp")},
            )
        else:
            logger.debug(
                "[Runner][%s] emit %-20s  data_keys=%s",
                self._run_id[:8],
                event_type,
                sorted(data.keys()),
            )

        if self._ws_broadcaster is None:
            logger.debug(
                "[Runner][%s] emit %r — no ws_broadcaster registered, event not sent",
                self._run_id[:8],
                event_type,
            )
            return

        try:
            self._ws_broadcaster(event_type, data)
        except Exception as exc:
            logger.warning(
                "[Runner][%s] ws_broadcaster raised for event %r: %s",
                self._run_id[:8],
                event_type,
                exc,
                exc_info=True,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Database helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _update_db_status(
        self,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """
        Update the PipelineRun.status (and optionally PipelineRun.error) in the DB.

        Args:
            status: "pending" | "running" | "completed" | "failed"
            error:  Optional error message (set when status == "failed").
        """
        logger.info(
            "[Runner][%s] DB status → %s%s",
            self._run_id[:8],
            status.upper(),
            f"  error={error[:120]!r}" if error else "",
        )
        try:
            run = self._db.get(PipelineRun, self._run_id)
            if run is None:
                logger.warning(
                    "[Runner][%s] PipelineRun not found in DB — cannot update status to %r.",
                    self._run_id[:8],
                    status,
                )
                return

            run.status = status
            if error:
                run.error = error[:2000]  # truncate long tracebacks
            if status in ("completed", "failed"):
                run.finished_at = datetime.now(timezone.utc)

            self._db.add(run)
            self._db.commit()
            logger.debug(
                "[Runner][%s] DB commit OK  status=%s", self._run_id[:8], status
            )

        except Exception as exc:
            logger.exception(
                "[Runner][%s] Failed to update run status to %r: %s",
                self._run_id[:8],
                status,
                exc,
            )
            try:
                self._db.rollback()
            except Exception:
                pass

    def _update_agent_status(self, agent_id: str, status: str) -> None:
        """
        Update the per-agent status inside PipelineRun.agent_statuses (JSON blob).

        Args:
            agent_id: Agent slug (e.g. "requirement_analyzer").
            status:   Status string: waiting | running | done | error | skipped.
        """
        try:
            run = self._db.get(PipelineRun, self._run_id)
            if run is None:
                return
            run.set_agent_status(agent_id, status)
            self._db.add(run)
            self._db.commit()
        except Exception as exc:
            logger.debug(
                "[PipelineRunner][%s] Failed to update agent status %r: %s",
                self._run_id,
                agent_id,
                exc,
            )
            try:
                self._db.rollback()
            except Exception:
                pass

    def _save_result(
        self,
        stage: str,
        agent_id: str,
        output: Optional[dict[str, Any]],
    ) -> None:
        """
        Persist stage output as a PipelineResult row in the database.

        The output is JSON-serialised and stored in PipelineResult.output.
        This allows the frontend to retrieve intermediate results via
        GET /api/v1/pipeline/runs/{run_id}.

        Args:
            stage:    Pipeline stage name (e.g. "ingestion", "testcase").
            agent_id: Identifier for what produced this result.
            output:   The stage output dict (serialised to JSON string).
        """
        if output is None:
            return

        try:
            result = PipelineResult(
                run_id=self._run_id,
                stage=stage,
                agent_id=agent_id,
                output=json.dumps(output, default=str),
            )
            self._db.add(result)
            self._db.commit()
            logger.debug(
                "[PipelineRunner][%s] Saved result: stage=%r agent=%r bytes=%d",
                self._run_id,
                stage,
                agent_id,
                len(result.output),
            )
        except Exception as exc:
            logger.warning(
                "[PipelineRunner][%s] Failed to save stage result %r: %s",
                self._run_id,
                stage,
                exc,
            )
            try:
                self._db.rollback()
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Result builder
    # ─────────────────────────────────────────────────────────────────────────

    def _build_result(
        self,
        document_name: str,
        status: str,
        t_start: float,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Build the final return dict summarising the pipeline run.

        Args:
            document_name: Source document name.
            status:        Final pipeline status ("completed" | "failed").
            t_start:       ``time.monotonic()`` timestamp from the start.
            error:         Optional error message.

        Returns:
            Flat dict with all stage outputs and metadata.
        """
        duration = round(time.monotonic() - t_start, 2)
        now = datetime.now(timezone.utc).isoformat()

        return {
            "run_id": self._run_id,
            "document_name": document_name,
            "status": status,
            "duration_seconds": duration,
            "finished_at": now,
            "error": error,
            # Stage outputs (None if that stage was not reached or failed)
            "ingestion": self._ingestion_output,
            "testcase": self._testcase_output,
            "execution": self._execution_output,
            "report": self._report_output,
            # High-level metrics for quick access
            "metrics": self._compute_summary_metrics(),
        }

    def _compute_summary_metrics(self) -> dict[str, Any]:
        """
        Compute high-level summary metrics from the accumulated stage outputs.

        Returns:
            Dict with: requirements_count, test_cases_count, pass_rate,
            coverage_percentage, and any other quick-access stats.
        """
        metrics: dict[str, Any] = {
            "requirements_count": 0,
            "test_cases_count": 0,
            "execution_total": 0,
            "execution_passed": 0,
            "pass_rate": 0.0,
            "coverage_percentage": 0.0,
        }

        if self._ingestion_output:
            metrics["requirements_count"] = len(
                self._ingestion_output.get("requirements", [])
            )

        if self._testcase_output:
            metrics["test_cases_count"] = self._testcase_output.get(
                "total_test_cases", len(self._testcase_output.get("test_cases", []))
            )

        if self._execution_output:
            summary = self._execution_output.get("summary", {})
            metrics["execution_total"] = summary.get("total", 0)
            metrics["execution_passed"] = summary.get("passed", 0)
            metrics["pass_rate"] = summary.get("pass_rate", 0.0)

        if self._report_output:
            metrics["coverage_percentage"] = self._report_output.get(
                "coverage_percentage", 0.0
            )

        return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Async wrapper
# ─────────────────────────────────────────────────────────────────────────────


async def run_pipeline_async(
    db: Session,
    run_id: str,
    file_path: str | Path,
    document_name: Optional[str] = None,
    run_profile_id: Optional[int] = None,
    ws_broadcaster: Optional[Callable] = None,
    mock_mode: Optional[bool] = None,
    environment: str = "default",
    skip_execution: bool = False,
    execution_config: Optional[dict[str, Any]] = None,
    ingestion_options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Async convenience wrapper around :class:`PipelineRunner`.

    Runs the synchronous PipelineRunner in the default asyncio executor so it
    doesn't block the event loop.

    The ``ws_broadcaster`` callable, if supplied, should accept
    ``(event_type: str, data: dict)`` and can be either sync or coroutine.
    When it's a coroutine, this wrapper schedules it via ``asyncio.ensure_future``.

    Args:
        db:               SQLAlchemy session (caller owns lifecycle).
        run_id:           UUID of the pipeline run.
        file_path:        Path to the document to process.
        document_name:    Optional display name.
        run_profile_id:   Optional LLM profile override.
        ws_broadcaster:   Optional async or sync progress callback.
        mock_mode:        Force mock mode.
        environment:      Target execution environment.
        skip_execution:   Skip Execution + Reporting stages.
        execution_config: Execution crew overrides.
        ingestion_options: Ingestion crew overrides.

    Returns:
        The same dict returned by :meth:`PipelineRunner.run`.
    """
    import asyncio

    loop = asyncio.get_event_loop()

    # Wrap an async broadcaster so it can be called synchronously
    sync_broadcaster: Optional[ProgressCallback] = None
    if ws_broadcaster is not None:
        import inspect

        if inspect.iscoroutinefunction(ws_broadcaster):

            def sync_broadcaster(event_type: str, data: dict[str, Any]) -> None:  # noqa: E306
                asyncio.ensure_future(ws_broadcaster(event_type, data))
        else:
            sync_broadcaster = ws_broadcaster  # type: ignore[assignment]

    runner = PipelineRunner(
        db=db,
        run_id=run_id,
        run_profile_id=run_profile_id,
        ws_broadcaster=sync_broadcaster,
        mock_mode=mock_mode,
        environment=environment,
    )

    # Run the synchronous pipeline in a thread pool so we don't block the loop
    result = await loop.run_in_executor(
        None,
        lambda: runner.run(
            file_path=file_path,
            document_name=document_name,
            ingestion_options=ingestion_options,
            execution_config=execution_config,
            skip_execution=skip_execution,
        ),
    )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point (for quick manual testing)
# ─────────────────────────────────────────────────────────────────────────────


def _cli_main() -> None:  # pragma: no cover
    """
    Quick manual test: python -m app.core.pipeline_runner <file_path>
    """
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m app.core.pipeline_runner <file_path> [run_id]")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    run_id = sys.argv[2] if len(sys.argv) > 2 else "test-run-cli"

    from app.db.database import get_db

    with next(get_db()) as db:
        runner = PipelineRunner(
            db=db,
            run_id=run_id,
            mock_mode=True,  # always mock in CLI test
        )
        result = runner.run(file_path=file_path)

    print("\n" + "=" * 60)
    print("Pipeline result:")
    print(json.dumps(result["metrics"], indent=2, default=str))
    print(f"\nStatus : {result['status']}")
    print(f"Duration: {result['duration_seconds']}s")
    if result.get("error"):
        print(f"Error  : {result['error']}")


if __name__ == "__main__":
    _cli_main()
