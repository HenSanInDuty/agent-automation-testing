from __future__ import annotations

"""
crews/reporting_crew.py
───────────────────────
Reporting crew — 3 CrewAI agents running sequentially.

Pipeline:
    coverage_analyzer    → post-execution requirement & scenario coverage
    root_cause_analyzer  → failure pattern grouping & root-cause mapping
    report_generator     → final executive + technical report

Input  (from ExecutionCrew output):
    test_cases_json         : list[dict]  – TestCase objects
    execution_results_json  : list[dict]  – TestExecutionResult objects
    requirements_json       : list[dict]  – original RequirementItem objects (optional)
    document_name           : str         – display name of the source document

Output (dict that conforms to PipelineReport schema):
    coverage_percentage     : float
    coverage_analysis       : dict   (PostExecutionCoverage)
    root_cause_analysis     : list   (list of RootCause dicts)
    executive_summary       : str
    recommendations         : list[str]
    risk_items              : list[str]
    total_test_cases        : int
    pass_rate               : float
    metrics                 : dict
    generated_at            : str

Mock mode produces a deterministic report without any LLM calls.

Usage::

    from app.crews.reporting_crew import ReportingCrew

    crew = ReportingCrew(db=session, run_id="abc-123")
    report = crew.run({
        "test_cases_json": [...],
        "execution_results_json": [...],
        "requirements_json": [...],    # optional
        "document_name": "spec.pdf",
    })
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.crews.base_crew import BaseCrew, ProgressCallback

logger = logging.getLogger(__name__)

# ── Optional CrewAI imports ───────────────────────────────────────────────────
try:
    from crewai import Crew, Process, Task  # type: ignore[import-untyped]

    _CREWAI_AVAILABLE = True
except ImportError:
    Crew = None  # type: ignore[assignment,misc]
    Process = None  # type: ignore[assignment,misc]
    Task = None  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False


class ReportingCrew(BaseCrew):
    """
    3-agent Sequential CrewAI crew that produces the final pipeline report.

    Agents (in execution order):
        1. coverage_analyzer    – post-execution requirement coverage
        2. root_cause_analyzer  – failure root-cause analysis
        3. report_generator     – comprehensive executive + technical report

    Attributes:
        stage:     Always ``"reporting"``.
        agent_ids: The three agent slugs managed by this crew.
    """

    stage = "reporting"
    agent_ids = [
        "coverage_analyzer",
        "root_cause_analyzer",
        "report_generator",
    ]

    def __init__(
        self,
        db: Session,
        run_id: str,
        run_profile_id: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
    ) -> None:
        super().__init__(
            db=db,
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the Reporting crew and return a PipelineReport-compatible dict.

        Args:
            input_data: Must contain:
                ``test_cases_json``        (list[dict])  – TestCase objects
                ``execution_results_json`` (list[dict])  – TestExecutionResult objects
                ``requirements_json``      (list[dict])  – original requirements (optional)
                ``document_name``          (str)         – document display name
                ``execution_summary``      (dict)        – ExecutionSummary dict (optional)
                ``mock_mode``              (bool)        – override instance mock_mode

        Returns:
            Dict conforming to :class:`~app.schemas.pipeline_io.PipelineReport`.

        Raises:
            ImportError: If crewai is not installed and mock_mode is False.
        """
        test_cases: list[dict] = list(input_data.get("test_cases_json") or [])
        exec_results: list[dict] = list(input_data.get("execution_results_json") or [])
        requirements: list[dict] = list(input_data.get("requirements_json") or [])
        document_name: str = str(input_data.get("document_name") or "uploaded document")
        exec_summary: Optional[dict] = input_data.get("execution_summary")

        # Allow per-call mock_mode override
        mock_mode: bool = bool(input_data.get("mock_mode", self._is_mock_mode()))

        self._emit_stage_started(agent_count=len(self.agent_ids))
        self._emit_log(f"Starting reporting crew for '{document_name}'")

        if mock_mode:
            self._emit_log("Mock mode — producing deterministic report without LLM")
            result = self._mock_run(
                test_cases=test_cases,
                exec_results=exec_results,
                requirements=requirements,
                exec_summary=exec_summary,
                document_name=document_name,
            )
        else:
            if not _CREWAI_AVAILABLE:
                raise ImportError(
                    "crewai is not installed. "
                    "On Linux/macOS run: uv add crewai. "
                    "On Windows use Docker or WSL2 for crew execution. "
                    "Alternatively pass mock_mode=True to skip LLM calls."
                )
            result = self._real_run(
                test_cases=test_cases,
                exec_results=exec_results,
                requirements=requirements,
                exec_summary=exec_summary,
                document_name=document_name,
            )

        self._emit_stage_completed()
        self._emit_log(
            f"Reporting complete — coverage {result.get('coverage_percentage', 0):.1f}%"
        )
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Real CrewAI run
    # ─────────────────────────────────────────────────────────────────────────

    def _real_run(
        self,
        test_cases: list[dict],
        exec_results: list[dict],
        requirements: list[dict],
        exec_summary: Optional[dict],
        document_name: str,
    ) -> dict[str, Any]:
        """
        Build and execute the CrewAI sequential crew, then parse the output.

        The crew uses ``Process.sequential`` — each agent's output is automatically
        made available as context to the next agent by CrewAI's context injection.
        """
        from app.core.agent_factory import AgentFactory
        from app.tasks.reporting_tasks import (
            make_coverage_analyzer_task,
            make_report_generator_task,
            make_root_cause_task,
        )

        factory = AgentFactory(self._db, run_profile_id=self._run_profile_id)

        # ── Build agents ──────────────────────────────────────────────────────
        self._emit_log("Building reporting agents from DB configuration")
        try:
            agents = factory.build_for_stage("reporting")
        except Exception as exc:
            logger.error(
                "[ReportingCrew][%s] Failed to build agents: %s", self._run_id, exc
            )
            raise

        coverage_agent = agents.get("coverage_analyzer")
        root_cause_agent = agents.get("root_cause_analyzer")
        report_agent = agents.get("report_generator")

        if not all([coverage_agent, root_cause_agent, report_agent]):
            missing = [
                k
                for k, v in {
                    "coverage_analyzer": coverage_agent,
                    "root_cause_analyzer": root_cause_agent,
                    "report_generator": report_agent,
                }.items()
                if v is None
            ]
            raise ValueError(
                f"Required reporting agents not found in DB: {missing}. "
                "Run the database seeder to create default agent configs."
            )

        # ── Build tasks ───────────────────────────────────────────────────────
        self._emit_agent_started("coverage_analyzer", "Coverage Analyzer")

        t_coverage = make_coverage_analyzer_task(
            agent=coverage_agent,
            test_cases_json=test_cases,
            execution_results_json=exec_results,
            requirements_json=requirements if requirements else None,
        )

        self._emit_agent_started("root_cause_analyzer", "Root Cause Analyzer")

        t_root_cause = make_root_cause_task(
            agent=root_cause_agent,
            execution_results_json=exec_results,
            test_cases_json=test_cases if test_cases else None,
            context_tasks=[t_coverage],
        )

        self._emit_agent_started("report_generator", "Report Generator")

        t_report = make_report_generator_task(
            agent=report_agent,
            context_tasks=[t_coverage, t_root_cause],
            execution_summary=exec_summary,
            document_name=document_name,
        )

        # ── Assemble and kick off crew ────────────────────────────────────────
        self._emit_log("Kicking off reporting crew (sequential process)")

        crew = Crew(
            agents=[coverage_agent, root_cause_agent, report_agent],
            tasks=[t_coverage, t_root_cause, t_report],
            process=Process.sequential,
            verbose=False,
        )

        try:
            crew_output = crew.kickoff()
        except Exception as exc:
            logger.error(
                "[ReportingCrew][%s] crew.kickoff() failed: %s",
                self._run_id,
                exc,
            )
            self._emit_log(f"Crew execution failed: {exc}", level="error")
            raise

        # ── Parse output ──────────────────────────────────────────────────────
        parsed = self._parse_json_output(crew_output)
        self._emit_agent_completed(
            "report_generator",
            output_preview=str(parsed.get("executive_summary", ""))[:200],
        )

        return self._normalise_report(parsed, exec_results, exec_summary)

    # ─────────────────────────────────────────────────────────────────────────
    # Mock run
    # ─────────────────────────────────────────────────────────────────────────

    def _mock_run(
        self,
        test_cases: list[dict],
        exec_results: list[dict],
        requirements: list[dict],
        exec_summary: Optional[dict],
        document_name: str,
    ) -> dict[str, Any]:
        """
        Produce a deterministic mock report without any LLM calls.

        Used when ``mock_mode=True`` or in tests.  All counts and percentages
        are computed from the actual input data so the output is realistic.
        """
        # ── Compute metrics from real data ────────────────────────────────────
        total_tc = len(test_cases)
        total_exec = len(exec_results)

        status_counts: dict[str, int] = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "error": 0,
        }
        for r in exec_results:
            s = str(r.get("status", "error")).lower()
            status_counts[s] = status_counts.get(s, 0) + 1

        passed = status_counts["passed"]
        failed = status_counts["failed"]
        skipped = status_counts["skipped"]
        errors = status_counts["error"]
        pass_rate = round(passed / total_exec * 100, 1) if total_exec > 0 else 0.0
        duration = exec_summary.get("duration_seconds", 0.0) if exec_summary else 0.0

        # ── Agent 1: mock coverage analysis ──────────────────────────────────
        self._emit_agent_started("coverage_analyzer", "Coverage Analyzer")

        req_ids = [
            str(r.get("id", f"REQ-{i:03d}")) for i, r in enumerate(requirements, 1)
        ]
        if not req_ids:
            # infer from test cases
            seen: set[str] = set()
            for tc in test_cases:
                rid = str(tc.get("requirement_id", "REQ-001"))
                seen.add(rid)
            req_ids = sorted(seen) or ["REQ-001"]

        total_reqs = len(req_ids)

        # Build req → test case mapping
        req_to_tcs: dict[str, list[str]] = {rid: [] for rid in req_ids}
        for tc in test_cases:
            rid = str(tc.get("requirement_id", req_ids[0]))
            tc_id = str(tc.get("id", "?"))
            req_to_tcs.setdefault(rid, []).append(tc_id)

        # Build tc → result mapping
        tc_to_status: dict[str, str] = {
            str(r.get("test_case_id", "?")): str(r.get("status", "error"))
            for r in exec_results
        }

        requirement_details = []
        covered_reqs = 0
        validated_reqs = 0
        failed_reqs: list[str] = []
        uncovered_reqs: list[str] = []

        for rid in req_ids:
            tc_ids = req_to_tcs.get(rid, [])
            tc_passed = sum(1 for t in tc_ids if tc_to_status.get(t) == "passed")
            tc_failed = sum(
                1 for t in tc_ids if tc_to_status.get(t) in ("failed", "error")
            )

            if not tc_ids:
                cov_status = "uncovered"
                uncovered_reqs.append(rid)
            elif tc_passed > 0:
                cov_status = "covered"
                covered_reqs += 1
                validated_reqs += 1
            elif tc_failed > 0:
                cov_status = "partial"
                covered_reqs += 1
                failed_reqs.append(rid)
            else:
                cov_status = "partial"
                covered_reqs += 1

            requirement_details.append(
                {
                    "requirement_id": rid,
                    "total_tests": len(tc_ids),
                    "passed_tests": tc_passed,
                    "failed_tests": tc_failed,
                    "coverage_status": cov_status,
                    "validation_status": (
                        "validated"
                        if tc_passed > 0
                        else "failing"
                        if tc_failed > 0
                        else "skipped"
                    ),
                    "defect_density": round(tc_failed / len(tc_ids), 2)
                    if tc_ids
                    else 0.0,
                }
            )

        cov_pct = round(covered_reqs / total_reqs * 100, 1) if total_reqs > 0 else 0.0
        val_pct = round(validated_reqs / total_reqs * 100, 1) if total_reqs > 0 else 0.0

        coverage_analysis = {
            "total_requirements": total_reqs,
            "covered_requirements": covered_reqs,
            "validated_requirements": validated_reqs,
            "coverage_percentage": cov_pct,
            "validation_percentage": val_pct,
            "uncovered_requirements": uncovered_reqs,
            "failed_requirements": failed_reqs,
            "by_type": {
                "functional": max(0, total_reqs - 1),
                "non_functional": min(1, total_reqs),
            },
            "by_priority": {
                "high": max(0, total_reqs // 3),
                "medium": total_reqs // 2,
                "low": total_reqs // 4,
            },
            "requirement_details": requirement_details,
            "coverage_gaps": [f"{rid} has no test cases" for rid in uncovered_reqs],
        }

        self._emit_agent_completed(
            "coverage_analyzer",
            output_preview=f"Coverage: {cov_pct}% ({covered_reqs}/{total_reqs} requirements)",
        )

        # ── Agent 2: mock root cause analysis ────────────────────────────────
        self._emit_agent_started("root_cause_analyzer", "Root Cause Analyzer")

        failures = [
            r
            for r in exec_results
            if str(r.get("status", "")).lower() in ("failed", "error")
        ]
        root_cause_analysis: list[dict] = []

        # Group by error pattern
        error_groups: dict[str, list[str]] = {}
        for f in failures:
            key = str(f.get("error_message") or f.get("actual_result") or "unknown")[
                :60
            ]
            tc_id = str(f.get("test_case_id", "?"))
            error_groups.setdefault(key, []).append(tc_id)

        for pattern, affected in error_groups.items():
            root_cause_analysis.append(
                {
                    "test_case_id": affected[0],
                    "failure_pattern": pattern[:100],
                    "probable_cause": "Mock analysis — verify manually",
                    "root_cause_category": "unknown",
                    "recommendation": (
                        f"Investigate {len(affected)} test(s) with this error pattern"
                    ),
                    "affected_tests": affected,
                    "severity": "medium",
                    "suggested_fix": "Review test configuration and target environment",
                }
            )

        self._emit_agent_completed(
            "root_cause_analyzer",
            output_preview=f"Found {len(root_cause_analysis)} distinct failure pattern(s)",
        )

        # ── Agent 3: mock report generation ──────────────────────────────────
        self._emit_agent_started("report_generator", "Report Generator")

        recommendations: list[str] = []
        risk_items: list[str] = []

        for rid in uncovered_reqs:
            recommendations.append(
                f"Add test cases for {rid} (currently has zero coverage)"
            )
            risk_items.append(f"{rid} has no test coverage")

        for rid in failed_reqs:
            risk_items.append(f"{rid} has failing test cases")

        for i, rca in enumerate(root_cause_analysis, start=1):
            recommendations.append(
                f"Priority {i}: {rca['recommendation']} "
                f"(affects {len(rca['affected_tests'])} test(s))"
            )

        if not recommendations:
            recommendations.append(
                f"All {total_reqs} requirements are covered and validated — "
                "continue monitoring in future runs."
            )

        exec_summary_str = (
            f"{passed}/{total_exec} tests passed ({pass_rate}%)"
            if total_exec > 0
            else "No tests were executed"
        )

        executive_summary = (
            f"Automated testing of '{document_name}' analyzed {total_reqs} requirement(s) "
            f"and generated {total_tc} test case(s). "
            f"{exec_summary_str}. "
            f"Requirement coverage is {cov_pct}% with {validated_reqs} requirements "
            f"fully validated. "
            + (
                f"{len(failed_reqs)} requirement(s) have failing tests and require attention."
                if failed_reqs
                else "No critical failures detected."
            )
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        report = {
            "coverage_percentage": cov_pct,
            "coverage_analysis": coverage_analysis,
            "root_cause_analysis": root_cause_analysis,
            "executive_summary": executive_summary,
            "recommendations": recommendations,
            "risk_items": risk_items,
            "generated_at": now_iso,
            "total_test_cases": total_tc,
            "pass_rate": pass_rate,
            "metrics": {
                "total": total_exec,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
                "duration_seconds": duration,
                "coverage_percentage": cov_pct,
                "validation_percentage": val_pct,
            },
        }

        self._emit_agent_completed(
            "report_generator",
            output_preview=executive_summary[:200],
        )

        return report

    # ─────────────────────────────────────────────────────────────────────────
    # Output normalisation
    # ─────────────────────────────────────────────────────────────────────────

    def _normalise_report(
        self,
        parsed: dict[str, Any],
        exec_results: list[dict],
        exec_summary: Optional[dict],
    ) -> dict[str, Any]:
        """
        Ensure the parsed crew output conforms to the PipelineReport schema.

        Fills in missing fields with computed defaults so downstream code
        can always rely on the complete structure.

        Args:
            parsed:       Raw parsed dict from the crew output.
            exec_results: Original execution results (used to fill missing metrics).
            exec_summary: Optional pre-computed summary dict.

        Returns:
            Normalised dict ready for :class:`~app.schemas.pipeline_io.PipelineReport`.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Compute metrics fallback from raw results if not present in crew output
        if not parsed.get("metrics") and exec_results:
            status_counts: dict[str, int] = {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "error": 0,
            }
            for r in exec_results:
                s = str(r.get("status", "error")).lower()
                status_counts[s] = status_counts.get(s, 0) + 1

            total = len(exec_results)
            passed = status_counts["passed"]
            parsed["metrics"] = {
                "total": total,
                "passed": passed,
                "failed": status_counts["failed"],
                "skipped": status_counts["skipped"],
                "errors": status_counts["error"],
                "duration_seconds": (
                    exec_summary.get("duration_seconds", 0.0) if exec_summary else 0.0
                ),
                "coverage_percentage": parsed.get("coverage_percentage", 0.0),
                "validation_percentage": 0.0,
            }
            parsed.setdefault(
                "pass_rate",
                round(passed / total * 100, 1) if total > 0 else 0.0,
            )

        # Ensure all required top-level fields exist
        parsed.setdefault("coverage_percentage", 0.0)
        parsed.setdefault("coverage_analysis", {})
        parsed.setdefault("root_cause_analysis", [])
        parsed.setdefault("executive_summary", "")
        parsed.setdefault("recommendations", [])
        parsed.setdefault("risk_items", [])
        parsed.setdefault("generated_at", now_iso)
        parsed.setdefault("total_test_cases", len(exec_results))
        parsed.setdefault("pass_rate", 0.0)
        parsed.setdefault("metrics", {})

        return parsed
