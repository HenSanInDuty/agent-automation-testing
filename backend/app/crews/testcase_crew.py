from __future__ import annotations

"""
crews/testcase_crew.py
──────────────────────
Test Case Generation crew — 10 CrewAI agents running in Sequential Process.

Pipeline (Tasks 1 → 10):
    1.  requirement_analyzer  – enrich & normalise requirements
    2.  scope_classifier      – classify test scope and risk
    3.  data_model_agent      – build test data model
    4.  rule_parser           – extract & formalise validation rules
    5.  test_condition_agent  – apply EP & BVA
    6.  dependency_agent      – map requirement dependencies
    7.  test_case_generator   – generate complete test cases  ← core output
    8.  automation_agent      – write automation scripts
    9.  coverage_agent_pre    – pre-execution coverage metrics
    10. report_agent_pre      – design-phase report (final output stored in DB)

In MOCK mode (MOCK_CREWS=true or mock_mode=True), the crew skips all LLM calls
and returns deterministic, structure-valid fake output derived from the input
requirements.  This allows end-to-end pipeline testing without a live LLM.

Usage::

    from app.crews.testcase_crew import TestcaseCrew

    crew = TestcaseCrew(db=session, run_id="abc-123", mock_mode=True)
    result = crew.run({"requirements": [...], "document_name": "spec.pdf"})
    # result is a TestCaseOutput.model_dump() dict
"""

import json
import logging
import re
import textwrap
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.schemas.pipeline_io import (
    AutomationReadiness,
    CoverageSummary,
    TestCase,
    TestCaseOutput,
    TestCategory,
    TestStep,
    TestType,
)

logger = logging.getLogger(__name__)

# ── Optional CrewAI import ────────────────────────────────────────────────────
try:
    from crewai import Crew, Process  # type: ignore[import-untyped]

    _CREWAI_AVAILABLE = True
except ImportError:
    Crew = None  # type: ignore[assignment,misc]
    Process = None  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False

# Ordered agent IDs for this crew
_AGENT_IDS: list[str] = [
    "requirement_analyzer",
    "scope_classifier",
    "data_model_agent",
    "rule_parser",
    "test_condition_agent",
    "dependency_agent",
    "test_case_generator",
    "automation_agent",
    "coverage_agent_pre",
    "report_agent_pre",
]


class TestcaseCrew(BaseCrew):
    """
    CrewAI Sequential crew that generates test cases from ingestion requirements.

    Attributes:
        stage:     "testcase"
        agent_ids: List of 10 agent_id slugs in execution order.
    """

    stage = "testcase"
    agent_ids = _AGENT_IDS

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
        Execute the Test Case Generation crew.

        Args:
            input_data: Must contain:
                ``requirements`` (list[dict]) – IngestionOutput.requirements
                ``document_name`` (str)       – source document name (for context)
                ``mock_mode`` (bool)          – optional per-call mock override

            Optional keys:
                ``environment`` (str) – target test environment (passed to context)

        Returns:
            ``TestCaseOutput.model_dump()`` — plain dict with full test case data.
        """
        requirements_json: list[dict] = input_data.get("requirements", [])
        document_name: str = input_data.get("document_name", "unknown document")
        per_call_mock: Optional[bool] = input_data.get("mock_mode")

        # Resolve mock mode (per-call arg wins over constructor setting)
        use_mock = per_call_mock if per_call_mock is not None else self._is_mock_mode()

        self._emit_log(
            f"Starting Test Case Generation for '{document_name}' "
            f"({len(requirements_json)} requirement(s), mock={use_mock})"
        )

        if not requirements_json:
            self._emit_log(
                "No requirements to process — returning empty TestCaseOutput",
                level="warning",
            )
            return TestCaseOutput(
                test_cases=[],
                total_test_cases=0,
                design_notes=["No requirements were provided to the Test Case crew."],
            ).model_dump()

        try:
            if use_mock:
                result = self._mock_run(requirements_json, document_name)
            else:
                result = self._crewai_run(requirements_json, document_name)
        except Exception as exc:
            error_msg = f"TestcaseCrew.run() failed: {exc}"
            logger.exception("[TestcaseCrew][%s] %s", self._run_id, error_msg)
            self._emit_log(error_msg, level="error")
            raise

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Real CrewAI run
    # ─────────────────────────────────────────────────────────────────────────

    def _crewai_run(
        self,
        requirements_json: list[dict],
        document_name: str,
    ) -> dict[str, Any]:
        """
        Execute the full 10-agent CrewAI sequential pipeline.

        Builds agents from DB via AgentFactory, creates tasks via task factories,
        assembles a Crew, kicks it off, and parses the output.
        """
        if not _CREWAI_AVAILABLE:
            raise ImportError(
                "crewai is not installed. "
                "Run: uv add crewai  (Linux/macOS)  "
                "or use Docker / WSL2 on Windows."
            )

        from app.core.agent_factory import AgentFactory
        from app.tasks.testcase_tasks import (
            make_automation_agent_task,
            make_coverage_pre_task,
            make_data_model_task,
            make_dependency_task,
            make_report_pre_task,
            make_requirement_analyzer_task,
            make_rule_parser_task,
            make_scope_classifier_task,
            make_test_case_generator_task,
            make_test_condition_task,
        )

        # ── Build agents ──────────────────────────────────────────────────────
        self._emit_log("Building agents from database configuration …")
        factory = AgentFactory(self._db, run_profile_id=self._run_profile_id)

        agents = {}
        for agent_id in _AGENT_IDS:
            # agent.started is emitted via task_callback during kickoff, not here
            try:
                agents[agent_id] = factory.build(agent_id)
                logger.debug("[TestcaseCrew] Built agent: %s", agent_id)
            except Exception as exc:
                self._emit_agent_failed(agent_id, str(exc))
                raise RuntimeError(
                    f"Failed to build agent '{agent_id}': {exc}"
                ) from exc

        # ── Build tasks in dependency order ───────────────────────────────────
        self._emit_log("Assembling task pipeline …")

        t1 = make_requirement_analyzer_task(
            agents["requirement_analyzer"], requirements_json
        )
        t2 = make_scope_classifier_task(agents["scope_classifier"], [t1])
        t3 = make_data_model_task(agents["data_model_agent"], [t1, t2])
        t4 = make_rule_parser_task(agents["rule_parser"], [t1, t2, t3])
        t5 = make_test_condition_task(agents["test_condition_agent"], [t1, t2, t3, t4])
        t6 = make_dependency_task(agents["dependency_agent"], [t1, t2, t5])
        t7 = make_test_case_generator_task(
            agents["test_case_generator"], [t1, t2, t3, t4, t5, t6]
        )
        t8 = make_automation_agent_task(agents["automation_agent"], [t7])
        t9 = make_coverage_pre_task(agents["coverage_agent_pre"], [t1, t7, t8])
        t10 = make_report_pre_task(
            agents["report_agent_pre"], [t1, t2, t3, t4, t5, t6, t7, t8, t9]
        )

        tasks = [t1, t2, t3, t4, t5, t6, t7, t8, t9, t10]

        # ── Task callback: relay per-task completion as agent events ──────────
        # tasks and _AGENT_IDS are in the same sequential order, so we can use
        # a simple counter to know which agent just finished.
        _task_idx: list[int] = [0]

        def _on_task_done(task_output: Any) -> None:  # noqa: ANN001
            idx = _task_idx[0]
            if idx < len(_AGENT_IDS):
                preview = str(getattr(task_output, "raw", task_output))[:200]
                self._emit_agent_completed(_AGENT_IDS[idx], output_preview=preview)
                self._emit_log(
                    f"[{_AGENT_IDS[idx]}] completed ({idx + 1}/{len(_AGENT_IDS)})"
                )
            _task_idx[0] += 1
            nxt = _task_idx[0]
            if nxt < len(_AGENT_IDS):
                self._emit_agent_started(_AGENT_IDS[nxt])
                self._emit_log(f"[{_AGENT_IDS[nxt]}] started …")

        # ── Assemble and run the Crew ─────────────────────────────────────────
        self._emit_log(f"Kicking off CrewAI Sequential crew with {len(tasks)} tasks …")

        # Emit started for the first agent — subsequent ones fire via callback
        self._emit_agent_started(_AGENT_IDS[0])
        self._emit_log(f"[{_AGENT_IDS[0]}] started …")

        crew = Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=False,  # per-agent verbosity controlled by AgentConfig.verbose
            task_callback=_on_task_done,
        )

        try:
            crew_output = crew.kickoff()
        except Exception as exc:
            # Mark the in-flight agent as failed
            idx = _task_idx[0]
            if idx < len(_AGENT_IDS):
                self._emit_agent_failed(_AGENT_IDS[idx], str(exc))
            logger.exception("[TestcaseCrew][%s] Crew kickoff failed", self._run_id)
            raise RuntimeError(f"Crew kickoff failed: {exc}") from exc

        # ── Parse the final task (report_agent_pre) output ───────────────────
        raw_output = self._parse_json_output(crew_output)
        return self._build_output(raw_output, requirements_json, document_name)

    # ─────────────────────────────────────────────────────────────────────────
    # Mock run (no LLM)
    # ─────────────────────────────────────────────────────────────────────────

    def _mock_run(
        self,
        requirements_json: list[dict],
        document_name: str,
    ) -> dict[str, Any]:
        """
        Produce deterministic, structure-valid mock output without calling any LLM.

        Generates one positive API test case per requirement plus one negative
        test case for requirements tagged as high-priority.

        Args:
            requirements_json: List of RequirementItem dicts.
            document_name:     Source document name.

        Returns:
            ``TestCaseOutput.model_dump()`` dict with synthetic test cases.
        """
        self._emit_log("Mock mode: generating synthetic test cases …")

        test_cases: list[TestCase] = []
        tc_counter = 1

        for req_idx, req in enumerate(requirements_json, start=1):
            req_id = str(req.get("id", "REQ-001"))
            title = str(req.get("title", "Untitled requirement"))
            priority = str(req.get("priority", "medium")).lower()
            tags = list(req.get("tags", []))

            # Infer API endpoint from requirement title
            endpoint_slug = _title_to_endpoint_slug(title)

            # --- Positive test case ---
            self._emit_agent_started("test_case_generator", "Test Case Generator")
            pos_tc = TestCase(
                id=f"TC-{tc_counter:03d}",
                requirement_id=req_id,
                title=f"[MOCK] {title} – happy path",
                description=f"Verify that {title.lower()} works correctly with valid input.",
                preconditions="System is running and accessible.",
                steps=[
                    TestStep(
                        step_number=1,
                        action=f"Send a valid POST request to {endpoint_slug}",
                        expected_result="System accepts the request and returns 200 OK",
                    ),
                    TestStep(
                        step_number=2,
                        action="Verify the response body contains expected fields",
                        expected_result="Response body matches the expected schema",
                    ),
                ],
                expected_result=f"System processes the request successfully for: {title}",
                test_type=TestType.API,
                category=TestCategory.POSITIVE,
                priority=priority,
                tags=tags + ["mock"],
                automation_script=_generate_mock_script(
                    tc_id=f"TC-{tc_counter:03d}",
                    endpoint=endpoint_slug,
                    method="POST",
                    expected_status=200,
                ),
                api_endpoint=endpoint_slug,
                http_method="POST",
                request_body={"mock_field": "valid_value"},
                expected_status_code=200,
            )
            test_cases.append(pos_tc)
            self._emit_agent_completed(
                "test_case_generator",
                output_preview=f"Generated {pos_tc.id}: {pos_tc.title}",
            )
            tc_counter += 1

            # --- Negative test case for high/medium priority ---
            if priority in ("high", "medium"):
                self._emit_agent_started("test_case_generator", "Test Case Generator")
                neg_tc = TestCase(
                    id=f"TC-{tc_counter:03d}",
                    requirement_id=req_id,
                    title=f"[MOCK] {title} – invalid input",
                    description=(
                        f"Verify that {title.lower()} rejects invalid or missing input "
                        "with the appropriate error response."
                    ),
                    preconditions="System is running and accessible.",
                    steps=[
                        TestStep(
                            step_number=1,
                            action=f"Send a POST request to {endpoint_slug} with missing required fields",
                            expected_result="System rejects the request with 400 Bad Request",
                        ),
                        TestStep(
                            step_number=2,
                            action="Verify the response body contains an error message",
                            expected_result="Response body contains 'error' or 'message' field",
                        ),
                    ],
                    expected_result=(
                        f"System returns 400 Bad Request with a descriptive error message "
                        f"for invalid input on: {title}"
                    ),
                    test_type=TestType.API,
                    category=TestCategory.NEGATIVE,
                    priority=priority,
                    tags=tags + ["mock", "negative"],
                    automation_script=_generate_mock_script(
                        tc_id=f"TC-{tc_counter:03d}",
                        endpoint=endpoint_slug,
                        method="POST",
                        expected_status=400,
                    ),
                    api_endpoint=endpoint_slug,
                    http_method="POST",
                    request_body={},
                    expected_status_code=400,
                )
                test_cases.append(neg_tc)
                self._emit_agent_completed(
                    "test_case_generator",
                    output_preview=f"Generated {neg_tc.id}: {neg_tc.title}",
                )
                tc_counter += 1

            self._emit(
                "agent.progress",
                {
                    "agent_id": "test_case_generator",
                    "message": f"Requirement {req_idx}/{len(requirements_json)} processed",
                    "progress": round(req_idx / len(requirements_json) * 100),
                },
            )

        # ── Emit remaining agent started/completed events ─────────────────────
        for agent_id in ["automation_agent", "coverage_agent_pre", "report_agent_pre"]:
            self._emit_agent_started(agent_id)
            self._emit_agent_completed(
                agent_id, output_preview=f"[mock] {agent_id} done"
            )

        # ── Build coverage summary ────────────────────────────────────────────
        req_ids = {str(r.get("id", "REQ-?")) for r in requirements_json}
        covered_req_ids = {tc.requirement_id for tc in test_cases}
        uncovered = sorted(req_ids - covered_req_ids)

        coverage_summary = CoverageSummary(
            total_requirements=len(req_ids),
            covered_requirements=len(covered_req_ids),
            coverage_percentage=round(
                len(covered_req_ids) / max(len(req_ids), 1) * 100, 1
            ),
            uncovered_requirements=uncovered,
            by_type={"functional": len(req_ids)},
            by_priority={
                "high": sum(
                    1 for r in requirements_json if r.get("priority") == "high"
                ),
                "medium": sum(
                    1 for r in requirements_json if r.get("priority") == "medium"
                ),
                "low": sum(1 for r in requirements_json if r.get("priority") == "low"),
            },
            by_category={
                "positive": sum(
                    1 for tc in test_cases if tc.category == TestCategory.POSITIVE
                ),
                "negative": sum(
                    1 for tc in test_cases if tc.category == TestCategory.NEGATIVE
                ),
            },
            coverage_gaps=(
                [f"No tests for: {r}" for r in uncovered] if uncovered else []
            ),
        )

        automation_readiness = AutomationReadiness(
            total_automated=len(test_cases),
            automation_percentage=100.0,
            frameworks_used=["pytest_httpx"],
        )

        output = TestCaseOutput(
            test_cases=test_cases,
            total_test_cases=len(test_cases),
            coverage_summary=coverage_summary,
            automation_readiness=automation_readiness,
            design_notes=[
                "[MOCK] Test cases generated by deterministic mock — no LLM was called.",
                f"Generated {len(test_cases)} test case(s) from {len(requirements_json)} requirement(s).",
            ],
            risks=(
                [f"Requirement '{r}' has no test cases." for r in uncovered]
                if uncovered
                else []
            ),
            recommendations=[
                "Enable a real LLM profile to generate production-quality test cases.",
                "Review mock test cases and expand with domain-specific scenarios.",
            ],
        )

        self._emit_log(
            f"Mock run complete: {len(test_cases)} test case(s) generated", level="info"
        )
        return output.model_dump()

    # ─────────────────────────────────────────────────────────────────────────
    # Output normalisation
    # ─────────────────────────────────────────────────────────────────────────

    def _build_output(
        self,
        raw: Any,
        requirements_json: list[dict],
        document_name: str,
    ) -> dict[str, Any]:
        """
        Normalise the raw CrewAI output into a ``TestCaseOutput`` model dict.

        The final task (report_agent_pre) is expected to return a JSON object
        matching the TestCaseOutput schema.  This method handles cases where
        the LLM produces partial or slightly off-schema output.

        Args:
            raw:               Parsed (or partially parsed) crew output.
            requirements_json: Original requirements (for fallback metrics).
            document_name:     Source document name (for logging).

        Returns:
            ``TestCaseOutput.model_dump()`` dict.
        """
        if not isinstance(raw, dict):
            logger.warning(
                "[TestcaseCrew][%s] Unexpected output type %s — wrapping.",
                self._run_id,
                type(raw).__name__,
            )
            raw = {"raw_output": raw}

        # ── Extract test_cases list ───────────────────────────────────────────
        raw_test_cases: list[dict] = raw.get("test_cases", [])
        if not isinstance(raw_test_cases, list):
            raw_test_cases = []

        test_cases: list[TestCase] = []
        for idx, tc_raw in enumerate(raw_test_cases, start=1):
            if not isinstance(tc_raw, dict):
                continue
            try:
                tc = _coerce_test_case(tc_raw, idx)
                test_cases.append(tc)
            except Exception as exc:
                logger.debug(
                    "[TestcaseCrew][%s] Could not coerce test case #%d: %s",
                    self._run_id,
                    idx,
                    exc,
                )

        # ── Extract or build coverage summary ────────────────────────────────
        raw_coverage = raw.get("coverage_summary") or {}
        if isinstance(raw_coverage, dict) and raw_coverage:
            try:
                coverage_summary = CoverageSummary(**raw_coverage)
            except Exception:
                coverage_summary = _build_coverage_summary(
                    test_cases, requirements_json
                )
        else:
            coverage_summary = _build_coverage_summary(test_cases, requirements_json)

        # ── Extract or build automation readiness ────────────────────────────
        raw_auto = raw.get("automation_readiness") or {}
        if isinstance(raw_auto, dict) and raw_auto:
            try:
                automation_readiness = AutomationReadiness(**raw_auto)
            except Exception:
                automation_readiness = _build_automation_readiness(test_cases)
        else:
            automation_readiness = _build_automation_readiness(test_cases)

        output = TestCaseOutput(
            test_cases=test_cases,
            total_test_cases=len(test_cases),
            coverage_summary=coverage_summary,
            automation_readiness=automation_readiness,
            design_notes=_coerce_str_list(raw.get("design_notes")),
            risks=_coerce_str_list(raw.get("risks")),
            recommendations=_coerce_str_list(raw.get("recommendations")),
        )

        self._emit_log(
            f"Test case generation complete: {len(test_cases)} test case(s), "
            f"coverage={coverage_summary.coverage_percentage}%"
        )
        return output.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helper functions
# ─────────────────────────────────────────────────────────────────────────────


def _title_to_endpoint_slug(title: str) -> str:
    """
    Convert a requirement title to a plausible API endpoint slug.

    e.g. "User Login" → "/api/v1/user-login"
         "Create New Product" → "/api/v1/new-product"

    Args:
        title: Requirement title string.

    Returns:
        Lowercase hyphenated API endpoint path.
    """
    # Remove common stopwords
    stopwords = {"the", "a", "an", "is", "are", "of", "for", "and", "or", "with"}
    words = re.split(r"\W+", title.lower())
    slug_words = [w for w in words if w and w not in stopwords][:4]
    slug = "-".join(slug_words) or "resource"
    return f"/api/v1/{slug}"


def _generate_mock_script(
    tc_id: str,
    endpoint: str,
    method: str = "GET",
    expected_status: int = 200,
) -> str:
    """
    Generate a minimal pytest + httpx automation script for a mock test case.

    Args:
        tc_id:           Test case ID (e.g. "TC-001").
        endpoint:        API endpoint path (e.g. "/api/v1/users").
        method:          HTTP method (default "GET").
        expected_status: Expected HTTP status code (default 200).

    Returns:
        Python source code string (escaped for JSON storage).
    """
    func_name = f"test_{tc_id.lower().replace('-', '_')}"
    body_arg = ", json={'mock_field': 'valid_value'}" if method != "GET" else ""

    return textwrap.dedent(f"""\
        import os
        import httpx
        import pytest

        BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")


        def {func_name}():
            \"\"\"
            {tc_id}: Auto-generated mock test for endpoint {endpoint}.
            Expected status: {expected_status}
            \"\"\"
            response = httpx.{method.lower()}(
                f"{{BASE_URL}}{endpoint}"{body_arg},
                timeout=30,
            )
            assert response.status_code == {expected_status}, (
                f"Expected {expected_status}, got {{response.status_code}}: "
                f"{{response.text[:200]}}"
            )
    """)


def _coerce_test_case(raw: dict, fallback_idx: int) -> TestCase:
    """
    Coerce a raw dict (from LLM output) into a TestCase model.

    Applies lenient defaults for missing fields so partial LLM outputs
    don't cause hard failures.

    Args:
        raw:          Raw dict from LLM / crew output.
        fallback_idx: Index used to generate a fallback TC id if missing.

    Returns:
        A valid :class:`TestCase` instance.
    """
    # Coerce steps
    raw_steps = raw.get("steps") or []
    steps: list[TestStep] = []
    if isinstance(raw_steps, list):
        for i, s in enumerate(raw_steps, start=1):
            if isinstance(s, dict):
                steps.append(
                    TestStep(
                        step_number=int(s.get("step_number", i)),
                        action=str(s.get("action", f"Step {i}")),
                        expected_result=str(s.get("expected_result", "")),
                    )
                )
            elif isinstance(s, str):
                steps.append(TestStep(step_number=i, action=s, expected_result=""))

    # Coerce test_type
    raw_type = str(raw.get("test_type", "api")).lower()
    try:
        test_type = TestType(raw_type)
    except ValueError:
        test_type = TestType.API

    # Coerce category
    raw_cat = str(raw.get("category", "positive")).lower()
    try:
        category = TestCategory(raw_cat)
    except ValueError:
        category = TestCategory.POSITIVE

    return TestCase(
        id=str(raw.get("id") or f"TC-{fallback_idx:03d}"),
        requirement_id=str(raw.get("requirement_id") or "REQ-001"),
        title=str(raw.get("title") or f"Test case {fallback_idx}"),
        description=str(raw.get("description") or ""),
        preconditions=str(raw.get("preconditions") or ""),
        steps=steps,
        expected_result=str(raw.get("expected_result") or ""),
        test_type=test_type,
        category=category,
        priority=str(raw.get("priority") or "medium").lower(),
        tags=[str(t) for t in (raw.get("tags") or []) if t],
        automation_script=raw.get("automation_script"),
        api_endpoint=raw.get("api_endpoint"),
        http_method=raw.get("http_method"),
        request_headers=raw.get("request_headers"),
        request_body=raw.get("request_body"),
        expected_status_code=_safe_int(raw.get("expected_status_code")),
        ui_page=raw.get("ui_page"),
        ui_selector=raw.get("ui_selector"),
    )


def _build_coverage_summary(
    test_cases: list[TestCase],
    requirements_json: list[dict],
) -> CoverageSummary:
    """
    Build a CoverageSummary by computing coverage from test cases directly.

    Used as a fallback when the LLM didn't produce a valid coverage object.
    """
    req_ids = {str(r.get("id", "?")) for r in requirements_json}
    covered_ids = {tc.requirement_id for tc in test_cases}
    uncovered = sorted(req_ids - covered_ids)

    by_category: dict[str, int] = {}
    for tc in test_cases:
        key = tc.category.value
        by_category[key] = by_category.get(key, 0) + 1

    by_priority: dict[str, int] = {}
    for r in requirements_json:
        p = str(r.get("priority", "medium")).lower()
        by_priority[p] = by_priority.get(p, 0) + 1

    by_type: dict[str, int] = {}
    for r in requirements_json:
        t = str(r.get("type", "functional")).lower()
        by_type[t] = by_type.get(t, 0) + 1

    total = len(req_ids)
    covered = len(covered_ids)
    coverage_pct = round(covered / max(total, 1) * 100, 1)

    return CoverageSummary(
        total_requirements=total,
        covered_requirements=covered,
        coverage_percentage=coverage_pct,
        uncovered_requirements=uncovered,
        by_type=by_type,
        by_priority=by_priority,
        by_category=by_category,
        coverage_gaps=[f"Requirement {r} has no test cases" for r in uncovered],
    )


def _build_automation_readiness(test_cases: list[TestCase]) -> AutomationReadiness:
    """Build AutomationReadiness metrics from test case list."""
    automated = sum(1 for tc in test_cases if tc.automation_script)
    total = len(test_cases)
    pct = round(automated / max(total, 1) * 100, 1)

    # Determine frameworks used
    frameworks: set[str] = set()
    for tc in test_cases:
        if tc.automation_script:
            if "playwright" in (tc.automation_script or "").lower():
                frameworks.add("pytest_playwright")
            else:
                frameworks.add("pytest_httpx")

    return AutomationReadiness(
        total_automated=automated,
        automation_percentage=pct,
        frameworks_used=sorted(frameworks),
    )


def _coerce_str_list(value: Any) -> list[str]:
    """Safely coerce a value to a list of strings."""
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [value]
    return []


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
