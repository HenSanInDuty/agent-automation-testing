from __future__ import annotations

"""
crews/execution_crew.py
───────────────────────
Execution crew – 5-agent CrewAI Sequential pipeline.

Agents (in execution order):
    1. execution_orchestrator  – plan execution order & timeouts
    2. env_adapter             – resolve environment config (uses config_loader tool)
    3. test_runner             – execute API test cases  (uses api_runner tool)
    4. execution_logger        – aggregate logs & timing stats
    5. result_store            – consolidate final ExecutionOutput

Supports two modes:
    REAL mode  – requires crewai installed; builds CrewAI Crew and runs agents.
    MOCK mode  – bypasses CrewAI entirely; returns deterministic mock results
                 based on the input test cases. Useful on Windows (no crewai)
                 and in CI pipelines.

Mock mode is activated when:
    - ``mock_mode=True`` is passed to the constructor or in ``input_data``
    - the ``MOCK_CREWS=true`` environment variable is set
    - crewai is not installed (automatic fallback)

Usage::

    from app.crews.execution_crew import ExecutionCrew

    crew = ExecutionCrew(db=session, run_id="abc-123")
    result = crew.run({
        "test_cases": [...],      # list of TestCase dicts from TestcaseCrew
        "environment": "default", # optional target environment name
    })
    # result is an ExecutionOutput.model_dump() dict
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.schemas.pipeline_io import (
    ExecutionOutput,
    ExecutionStatus,
    ExecutionSummary,
    FailurePattern,
    TestExecutionResult,
    TimingStats,
)

logger = logging.getLogger(__name__)

# ── Optional CrewAI import ────────────────────────────────────────────────────
try:
    from crewai import Agent, Crew, Process, Task  # type: ignore[import-untyped]

    _CREWAI_AVAILABLE = True
    print("===============================checking from crew AI true")
except ImportError:
    _CREWAI_AVAILABLE = False
    print("===============================checking from crew AI false")

# Agent display names (used in progress events)
_DISPLAY_NAMES: dict[str, str] = {
    "execution_orchestrator": "Execution Orchestrator",
    "env_adapter": "Environment Adapter",
    "test_runner": "Test Runner",
    "execution_logger": "Execution Logger",
    "result_store": "Result Store Manager",
}


# ─────────────────────────────────────────────────────────────────────────────
# ExecutionCrew
# ─────────────────────────────────────────────────────────────────────────────


class ExecutionCrew(BaseCrew):
    """
    5-agent CrewAI Sequential crew for test execution.

    Attributes:
        stage:     Always "execution".
        agent_ids: Ordered list of the 5 execution agent IDs.
    """

    stage = "execution"
    agent_ids = [
        "execution_orchestrator",
        "env_adapter",
        "test_runner",
        "execution_logger",
        "result_store",
    ]

    def __init__(
        self,
        db: Session,
        run_id: str,
        run_profile_id: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        environment: str = "default",
    ) -> None:
        """
        Initialise the Execution crew.

        Args:
            db:                Active SQLAlchemy session.
            run_id:            UUID of the current pipeline run.
            run_profile_id:    Optional run-level LLM profile override.
            progress_callback: Optional progress event callback.
            mock_mode:         Force mock mode (overrides settings.MOCK_CREWS).
            environment:       Default target environment name (can be overridden in input_data).
        """
        super().__init__(
            db=db,
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )
        self._environment = environment

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the test execution pipeline.

        Args:
            input_data: Dictionary with at minimum:
                ``test_cases``  (list[dict]) – TestCase dicts from TestcaseCrew.
                ``environment`` (str)        – optional target environment name.
                ``mock_mode``   (bool)       – optional per-call mock override.
                ``execution_config`` (dict)  – optional timeout/mode overrides.

        Returns:
            ``ExecutionOutput.model_dump()`` — a plain dict with all test results.
        """
        test_cases: list[dict[str, Any]] = input_data.get("test_cases", [])
        environment: str = input_data.get("environment", self._environment)
        force_mock: Optional[bool] = input_data.get("mock_mode")
        execution_config: dict[str, Any] = input_data.get("execution_config", {})

        # Resolve mock mode: per-call arg overrides constructor arg
        use_mock = force_mock if force_mock is not None else self._is_mock_mode()
        # Auto-fallback to mock if crewai is not installed
        if not _CREWAI_AVAILABLE and not use_mock:
            logger.warning(
                "[ExecutionCrew][%s] crewai not installed — falling back to mock mode.",
                self._run_id,
            )
            use_mock = True

        self._emit_log(
            f"Starting execution of {len(test_cases)} test case(s) "
            f"on environment '{environment}' "
            f"({'mock' if use_mock else 'real'} mode)"
        )

        try:
            if use_mock:
                result = self._mock_run(test_cases, environment)
            else:
                result = self._real_run(test_cases, environment, execution_config)
        except Exception as exc:
            error_msg = f"Execution crew failed: {exc}"
            logger.exception(
                "[ExecutionCrew][%s] Unexpected error: %s", self._run_id, exc
            )
            self._emit_log(error_msg, level="error")
            # Return a minimal failed output so the pipeline can continue to reporting
            return self._error_output(test_cases, environment, error_msg)

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Real CrewAI execution
    # ─────────────────────────────────────────────────────────────────────────

    def _real_run(
        self,
        test_cases: list[dict[str, Any]],
        environment: str,
        execution_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute test cases using a real CrewAI Crew with LLM-backed agents."""
        from app.core.agent_factory import AgentFactory
        from app.tasks.execution_tasks import (
            make_env_adapter_task,
            make_execution_logger_task,
            make_execution_orchestrator_task,
            make_result_store_task,
            make_test_runner_task,
        )
        from app.tools.api_runner import APIRunnerTool
        from app.tools.config_loader import ConfigLoaderTool

        # ── Build agents ─────────────────────────────────────────────────────
        self._emit_log("Building execution agents from database configuration…")
        factory = AgentFactory(self._db, run_profile_id=self._run_profile_id)

        # Build each agent, injecting tools where applicable
        agent_objects: dict[str, Any] = {}
        tool_map: dict[str, list] = {
            "env_adapter": [ConfigLoaderTool()],
            "test_runner": [APIRunnerTool()],
        }

        for agent_id in self.agent_ids:
            # agent.started is emitted via task_callback during kickoff, not here
            try:
                agent = factory.build(agent_id)
                # Inject tools after building (crewai Agent supports `tools` attr)
                tools = tool_map.get(agent_id, [])
                if tools:
                    existing_tools = list(getattr(agent, "tools", []) or [])
                    agent.tools = existing_tools + tools
                agent_objects[agent_id] = agent
                logger.debug(
                    "[ExecutionCrew][%s] Built agent %r with %d tool(s)",
                    self._run_id,
                    agent_id,
                    len(tool_map.get(agent_id, [])),
                )
            except Exception as exc:
                self._emit_agent_failed(agent_id, str(exc))
                raise RuntimeError(
                    f"Failed to build execution agent {agent_id!r}: {exc}"
                ) from exc

        # ── Build tasks ──────────────────────────────────────────────────────
        self._emit_log("Building task chain…")

        t_orchestrator = make_execution_orchestrator_task(
            agent=agent_objects["execution_orchestrator"],
            test_cases_json=test_cases,
            execution_config=execution_config,
        )

        t_env = make_env_adapter_task(
            agent=agent_objects["env_adapter"],
            context_tasks=[t_orchestrator],
            environment=environment,
            test_cases_json=test_cases,
        )

        t_runner = make_test_runner_task(
            agent=agent_objects["test_runner"],
            context_tasks=[t_orchestrator, t_env],
            test_cases_json=test_cases,
        )

        t_logger = make_execution_logger_task(
            agent=agent_objects["execution_logger"],
            context_tasks=[t_env, t_runner],
        )

        t_store = make_result_store_task(
            agent=agent_objects["result_store"],
            context_tasks=[t_orchestrator, t_env, t_runner, t_logger],
        )

        # ── Task callback: relay per-task completion as agent events ──────────
        # self.agent_ids and the tasks list are in the same sequential order.
        _ordered_ids = list(self.agent_ids)
        _task_idx: list[int] = [0]

        def _on_task_done(task_output: Any) -> None:  # noqa: ANN001
            idx = _task_idx[0]
            if idx < len(_ordered_ids):
                agent_id = _ordered_ids[idx]
                preview = str(getattr(task_output, "raw", task_output))[:200]
                self._emit_agent_completed(agent_id, output_preview=preview)
                self._emit_log(
                    f"[{_DISPLAY_NAMES.get(agent_id, agent_id)}] completed"
                    f" ({idx + 1}/{len(_ordered_ids)})"
                )
            _task_idx[0] += 1
            nxt = _task_idx[0]
            if nxt < len(_ordered_ids):
                nid = _ordered_ids[nxt]
                self._emit_agent_started(nid, _DISPLAY_NAMES.get(nid, nid))
                self._emit_log(f"[{_DISPLAY_NAMES.get(nid, nid)}] started …")

        # ── Assemble and run crew ────────────────────────────────────────────
        self._emit_log("Launching CrewAI execution crew (sequential process)…")

        # Emit started for the first agent — subsequent ones fire via callback
        first_id = _ordered_ids[0]
        self._emit_agent_started(first_id, _DISPLAY_NAMES.get(first_id, first_id))
        self._emit_log(f"[{_DISPLAY_NAMES.get(first_id, first_id)}] started …")

        crew = Crew(
            agents=list(agent_objects.values()),
            tasks=[t_orchestrator, t_env, t_runner, t_logger, t_store],
            process=Process.sequential,
            verbose=False,
            task_callback=_on_task_done,
        )

        t0 = time.monotonic()
        try:
            raw_output = crew.kickoff()
        except Exception as exc:
            idx = _task_idx[0]
            if idx < len(_ordered_ids):
                self._emit_agent_failed(_ordered_ids[idx], str(exc))
            raise
        duration = time.monotonic() - t0

        self._emit_log(f"Crew kickoff completed in {duration:.1f}s — parsing output…")

        # ── Parse output ─────────────────────────────────────────────────────
        parsed = self._parse_json_output(raw_output)
        return self._normalise_output(parsed, environment, test_cases)

    # ─────────────────────────────────────────────────────────────────────────
    # Mock execution
    # ─────────────────────────────────────────────────────────────────────────

    def _mock_run(
        self,
        test_cases: list[dict[str, Any]],
        environment: str,
    ) -> dict[str, Any]:
        """
        Generate deterministic mock execution results without calling any LLM.

        Mock behaviour:
          - 80 % of API / integration tests → PASSED
          - 15 % → FAILED  (simulates realistic failure rate)
          -  5 % → SKIPPED (environment constraint simulation)
          - Priority-high tests are always PASSED (to avoid false alerts in demos)
          - Edge-case / boundary tests have a slightly higher failure rate (25 %)
          - Execution timing is simulated (50–500 ms per test)

        Args:
            test_cases:   List of TestCase dicts to simulate execution for.
            environment:  Environment name (included in output metadata).

        Returns:
            ExecutionOutput dict.
        """
        import hashlib

        self._emit_log(
            f"Mock mode: simulating execution of {len(test_cases)} test case(s)…"
        )

        results: list[TestExecutionResult] = []
        total_duration_ms = 0.0
        durations: list[float] = []

        for tc in test_cases:
            tc_id = str(tc.get("id", "TC-?"))
            priority = str(tc.get("priority", "medium")).lower()
            category = str(tc.get("category", "positive")).lower()
            http_method = str(tc.get("http_method", "GET")).upper()
            expected_code = tc.get("expected_status_code") or 200
            api_endpoint = tc.get("api_endpoint", "/api/mock")

            # ── Deterministic status via hash of tc_id ────────────────────
            # Using a hash keeps results consistent across runs for the same
            # test case IDs (useful for snapshot testing).
            h = int(hashlib.md5(tc_id.encode()).hexdigest()[:4], 16) % 100

            if priority == "high":
                # High-priority tests always pass in mock mode
                status = ExecutionStatus.PASSED
            elif category in ("edge_case", "boundary"):
                # Edge/boundary cases: 25 % failure rate
                status = ExecutionStatus.FAILED if h < 25 else ExecutionStatus.PASSED
            elif h < 5:
                status = ExecutionStatus.SKIPPED
            elif h < 20:
                status = ExecutionStatus.FAILED
            else:
                status = ExecutionStatus.PASSED

            # ── Simulated duration (50–500 ms, deterministic per tc_id) ──
            duration_ms = 50.0 + (h % 45) * 10.0  # 50–500 ms
            total_duration_ms += duration_ms
            durations.append(duration_ms)

            # ── Build mock response data ───────────────────────────────────
            if status == ExecutionStatus.PASSED:
                actual_code = expected_code
                actual_result = (
                    f"HTTP {actual_code} — response matches expected criteria"
                )
                actual_response: Optional[dict] = {"mock": True, "status": "ok"}
                error_msg: Optional[str] = None
                logs = [
                    f"Sending {http_method} {api_endpoint}",
                    f"Received {actual_code} in {duration_ms:.1f} ms",
                    f"Status code {actual_code} matches expected {expected_code} → PASSED",
                ]
            elif status == ExecutionStatus.FAILED:
                # Simulate a realistic failure scenario
                actual_code = (
                    400 if category == "negative" else (401 if h % 3 == 0 else 500)
                )
                actual_result = (
                    f"HTTP {actual_code} — "
                    f"{'Validation error' if actual_code == 400 else 'Unauthorized' if actual_code == 401 else 'Server error'}"
                )
                actual_response = {
                    "mock": True,
                    "error": actual_result,
                    "code": actual_code,
                }
                error_msg = (
                    f"Status code mismatch: expected {expected_code}, got {actual_code}"
                )
                logs = [
                    f"Sending {http_method} {api_endpoint}",
                    f"Received {actual_code} in {duration_ms:.1f} ms",
                    f"FAILED: {error_msg}",
                ]
            else:
                # SKIPPED
                actual_code = None
                actual_result = "Skipped: environment constraint"
                actual_response = None
                error_msg = None
                logs = [
                    f"SKIPPED: {tc_id} not applicable in '{environment}' environment"
                ]
                duration_ms = 0.0

            self._emit_agent_started(
                "test_runner",
                f"Test Runner → {tc_id}",
            )

            result = TestExecutionResult(
                test_case_id=tc_id,
                status=status,
                duration_ms=duration_ms,
                actual_result=actual_result,
                actual_status_code=actual_code,
                actual_response=actual_response,
                error_message=error_msg,
                timestamp=datetime.now(timezone.utc),
                logs=logs,
            )
            results.append(result)

            self._emit_agent_completed(
                "test_runner",
                f"{tc_id}: {status.value.upper()} ({duration_ms:.0f} ms)",
            )

        # ── Summary ───────────────────────────────────────────────────────────
        total = len(results)
        passed = sum(1 for r in results if r.status == ExecutionStatus.PASSED)
        failed = sum(1 for r in results if r.status == ExecutionStatus.FAILED)
        skipped = sum(1 for r in results if r.status == ExecutionStatus.SKIPPED)
        errors = sum(1 for r in results if r.status == ExecutionStatus.ERROR)
        pass_rate = round(passed / total * 100, 1) if total > 0 else 0.0

        # Timing stats
        exec_durations = [r.duration_ms for r in results if r.duration_ms > 0]
        if exec_durations:
            sorted_d = sorted(exec_durations)
            p95_idx = max(0, int(len(sorted_d) * 0.95) - 1)
            timing = TimingStats(
                min_ms=sorted_d[0],
                max_ms=sorted_d[-1],
                avg_ms=round(sum(sorted_d) / len(sorted_d), 2),
                p95_ms=sorted_d[p95_idx],
            )
        else:
            timing = TimingStats()

        # Failure patterns
        failure_patterns: list[FailurePattern] = []
        code_groups: dict[str, list[str]] = {}
        for r in results:
            if r.status in (ExecutionStatus.FAILED, ExecutionStatus.ERROR):
                code = str(r.actual_status_code or "error")
                code_groups.setdefault(code, []).append(r.test_case_id)
        for code, tc_ids in code_groups.items():
            if len(tc_ids) >= 1:
                failure_patterns.append(
                    FailurePattern(
                        pattern=f"HTTP {code}",
                        affected_tests=tc_ids,
                        occurrence_count=len(tc_ids),
                    )
                )

        summary = ExecutionSummary(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            pass_rate=pass_rate,
            duration_seconds=round(total_duration_ms / 1000, 2),
        )

        output = ExecutionOutput(
            results=results,
            summary=summary,
            environment=environment,
            timing_stats=timing,
            failure_patterns=failure_patterns,
            execution_notes=[
                f"Mock execution completed: {total} test case(s)",
                f"Pass rate: {pass_rate}%",
                f"Total simulated duration: {summary.duration_seconds}s",
                "Note: Results are mock/simulated — run in real mode for actual test execution.",
            ],
        )

        self._emit_log(
            f"Mock execution complete: {passed}/{total} passed ({pass_rate}%)"
        )
        return output.model_dump()

    # ─────────────────────────────────────────────────────────────────────────
    # Output normalisation
    # ─────────────────────────────────────────────────────────────────────────

    def _normalise_output(
        self,
        parsed: Any,
        environment: str,
        test_cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Validate and normalise the CrewAI crew output into an ExecutionOutput dict.

        Handles cases where the crew output:
          - Is already a valid ExecutionOutput-shaped dict → pass-through
          - Contains a ``results`` list but missing summary → compute summary
          - Is a ``raw_output`` fallback → build minimal error output

        Args:
            parsed:      Parsed JSON output from the crew (dict or list).
            environment: Environment name for the output metadata.
            test_cases:  Original test cases (used to fill missing result entries).

        Returns:
            ExecutionOutput.model_dump() dict.
        """
        if isinstance(parsed, dict) and "raw_output" in parsed and len(parsed) == 1:
            # Crew returned unparseable text
            logger.warning(
                "[ExecutionCrew][%s] Crew returned non-JSON output — "
                "generating minimal error output.",
                self._run_id,
            )
            return self._error_output(
                test_cases,
                environment,
                "Crew output could not be parsed as JSON: "
                + parsed["raw_output"][:200],
            )

        # Try to interpret as ExecutionOutput
        try:
            output = ExecutionOutput.model_validate(parsed)
            return output.model_dump()
        except Exception:
            pass

        # Try to extract results array from various shapes
        results_raw: list[dict[str, Any]] = []
        if isinstance(parsed, list):
            results_raw = parsed
        elif isinstance(parsed, dict):
            results_raw = parsed.get("results", [])

        if not results_raw:
            return self._error_output(
                test_cases,
                environment,
                "Crew output contained no results array.",
            )

        # Build TestExecutionResult objects from raw dicts
        results: list[TestExecutionResult] = []
        for raw in results_raw:
            if not isinstance(raw, dict):
                continue
            status_raw = str(raw.get("status", "error")).lower()
            try:
                status = ExecutionStatus(status_raw)
            except ValueError:
                status = ExecutionStatus.ERROR

            results.append(
                TestExecutionResult(
                    test_case_id=str(raw.get("test_case_id", "?")),
                    status=status,
                    duration_ms=float(raw.get("duration_ms", 0.0)),
                    actual_result=str(raw.get("actual_result", "")),
                    actual_status_code=raw.get("actual_status_code"),
                    actual_response=raw.get("actual_response"),
                    error_message=raw.get("error_message"),
                    logs=list(raw.get("logs", [])),
                )
            )

        total = len(results)
        passed = sum(1 for r in results if r.status == ExecutionStatus.PASSED)
        failed = sum(1 for r in results if r.status == ExecutionStatus.FAILED)
        skipped = sum(1 for r in results if r.status == ExecutionStatus.SKIPPED)
        errors = sum(1 for r in results if r.status == ExecutionStatus.ERROR)

        summary = ExecutionSummary(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            pass_rate=round(passed / total * 100, 1) if total > 0 else 0.0,
            duration_seconds=round(sum(r.duration_ms for r in results) / 1000, 2),
        )

        # Carry over extra fields from parsed dict
        timing_raw = parsed.get("timing_stats", {}) if isinstance(parsed, dict) else {}
        failure_patterns_raw = (
            parsed.get("failure_patterns", []) if isinstance(parsed, dict) else []
        )
        execution_notes = (
            parsed.get("execution_notes", []) if isinstance(parsed, dict) else []
        )

        timing = TimingStats(
            min_ms=float(timing_raw.get("min_ms", 0.0)),
            max_ms=float(timing_raw.get("max_ms", 0.0)),
            avg_ms=float(timing_raw.get("avg_ms", 0.0)),
            p95_ms=float(timing_raw.get("p95_ms", 0.0)),
        )

        failure_patterns = [
            FailurePattern(
                pattern=str(fp.get("pattern", "")),
                affected_tests=list(fp.get("affected_tests", [])),
                occurrence_count=int(fp.get("occurrence_count", 0)),
            )
            for fp in failure_patterns_raw
            if isinstance(fp, dict)
        ]

        output = ExecutionOutput(
            results=results,
            summary=summary,
            environment=environment,
            timing_stats=timing,
            failure_patterns=failure_patterns,
            execution_notes=execution_notes,
        )
        return output.model_dump()

    # ─────────────────────────────────────────────────────────────────────────
    # Error output helper
    # ─────────────────────────────────────────────────────────────────────────

    def _error_output(
        self,
        test_cases: list[dict[str, Any]],
        environment: str,
        error_message: str,
    ) -> dict[str, Any]:
        """
        Build a minimal ExecutionOutput where all test cases are marked as ERROR.

        Used as a fallback when the crew fails or produces unparseable output,
        so the pipeline can continue to the Reporting stage.

        Args:
            test_cases:    Original list of test case dicts.
            environment:   Target environment name.
            error_message: Description of what went wrong.

        Returns:
            ExecutionOutput.model_dump() with all statuses set to "error".
        """
        total = len(test_cases)
        results = [
            TestExecutionResult(
                test_case_id=str(tc.get("id", f"TC-{i + 1}")),
                status=ExecutionStatus.ERROR,
                duration_ms=0.0,
                actual_result=f"Execution crew failed: {error_message}",
                error_message=error_message,
                logs=[f"ERROR: execution crew did not complete — {error_message}"],
            )
            for i, tc in enumerate(test_cases)
        ]

        summary = ExecutionSummary(
            total=total,
            passed=0,
            failed=0,
            skipped=0,
            errors=total,
            pass_rate=0.0,
            duration_seconds=0.0,
        )

        output = ExecutionOutput(
            results=results,
            summary=summary,
            environment=environment,
            execution_notes=[
                f"EXECUTION FAILED: {error_message}",
                "All test cases marked as ERROR — please check agent configuration.",
            ],
        )
        return output.model_dump()
