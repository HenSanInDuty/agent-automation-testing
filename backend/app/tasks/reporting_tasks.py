from __future__ import annotations

"""
tasks/reporting_tasks.py
────────────────────────
Task factory functions for the Reporting crew (3 agents).

Agents covered:
    coverage_analyzer    – post-execution requirement & scenario coverage
    root_cause_analyzer  – failure pattern analysis and root-cause mapping
    report_generator     – final comprehensive executive + technical report

Each factory function accepts a ``crewai.Agent`` instance (built by AgentFactory)
and returns a configured ``crewai.Task``.  Input data is injected directly into
the task description so the LLM has full context without extra tool calls.

Usage::

    from app.tasks.reporting_tasks import (
        make_coverage_analyzer_task,
        make_root_cause_task,
        make_report_generator_task,
    )
"""

import json
import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# ── Optional CrewAI import ────────────────────────────────────────────────────
try:
    from crewai import Task  # type: ignore[import-untyped]

    _CREWAI_AVAILABLE = True
except ImportError:
    Task = None  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False

if TYPE_CHECKING:
    from crewai import Agent
    from crewai import Task as TaskType


# ─────────────────────────────────────────────────────────────────────────────
# Guard helper
# ─────────────────────────────────────────────────────────────────────────────


def _require_crewai() -> None:
    if not _CREWAI_AVAILABLE or Task is None:
        raise ImportError(
            "crewai is not installed. "
            "Run: uv add crewai  (Linux/macOS)  "
            "or use Docker / WSL2 on Windows."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _safe_json(obj: Any, max_items: int = 50) -> str:
    """
    Serialize *obj* to a compact JSON string for embedding in task descriptions.
    Lists are truncated to *max_items* to avoid blowing the context window.
    """
    if isinstance(obj, list) and len(obj) > max_items:
        truncated = obj[:max_items]
        suffix = f"\n... ({len(obj) - max_items} more items omitted)"
        return json.dumps(truncated, indent=2, ensure_ascii=False, default=str) + suffix
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


def _count_by_status(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for r in results:
        status = str(r.get("status", "error")).lower()
        counts[status] = counts.get(status, 0) + 1
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 – Coverage Analyzer
# ─────────────────────────────────────────────────────────────────────────────


def make_coverage_analyzer_task(
    agent: "Agent",
    test_cases_json: list[dict[str, Any]],
    execution_results_json: list[dict[str, Any]],
    requirements_json: list[dict[str, Any]] | None = None,
) -> "TaskType":
    """
    Build the post-execution coverage analysis task.

    This task runs after the Execution crew and measures:
    - What percentage of requirements were covered (at least one test executed)
    - What percentage were *validated* (at least one test passed)
    - Coverage breakdown by type, priority, and risk category
    - Identification of uncovered and still-failing requirements

    Args:
        agent:                   The coverage_analyzer CrewAI Agent.
        test_cases_json:         List of TestCase dicts from TestcaseCrew output.
        execution_results_json:  List of TestExecutionResult dicts from ExecutionCrew.
        requirements_json:       Optional original requirements list for deeper tracing.

    Returns:
        A configured ``crewai.Task`` instance.
    """
    _require_crewai()

    tc_count = len(test_cases_json)
    result_count = len(execution_results_json)
    status_counts = _count_by_status(execution_results_json)

    passed = status_counts["passed"]
    failed = status_counts["failed"]
    skipped = status_counts["skipped"]
    errors = status_counts["error"]
    pass_rate = round(passed / result_count * 100, 1) if result_count > 0 else 0.0

    # Build requirement → test cases mapping for context
    req_to_tcs: dict[str, list[str]] = {}
    for tc in test_cases_json:
        req_id = str(tc.get("requirement_id", "UNKNOWN"))
        tc_id = str(tc.get("id", "?"))
        req_to_tcs.setdefault(req_id, []).append(tc_id)

    # Build test case → result mapping
    tc_to_result: dict[str, str] = {}
    for result in execution_results_json:
        tc_id = str(result.get("test_case_id", "?"))
        status = str(result.get("status", "unknown"))
        tc_to_result[tc_id] = status

    mapping_str = _safe_json(
        [
            {
                "requirement_id": req_id,
                "test_case_ids": tc_ids,
                "statuses": [
                    tc_to_result.get(tc_id, "not_executed") for tc_id in tc_ids
                ],
            }
            for req_id, tc_ids in sorted(req_to_tcs.items())
        ],
        max_items=40,
    )

    req_section = ""
    if requirements_json:
        req_section = f"""
Original requirements ({len(requirements_json)} total):
{_safe_json(requirements_json, max_items=30)}
"""

    return Task(
        description=f"""You are the post-execution coverage analyzer.

Execution run statistics:
  - Total test cases designed : {tc_count}
  - Total test cases executed : {result_count}
  - Passed   : {passed}
  - Failed   : {failed}
  - Skipped  : {skipped}
  - Errors   : {errors}
  - Pass rate: {pass_rate}%
{req_section}
Requirement → Test Case → Result mapping:
{mapping_str}

Analyze coverage from TWO dimensions:

1. REQUIREMENT COVERAGE – which business requirements were tested and validated:
   - "covered"   = at least one test case executed for this requirement
   - "validated" = at least one test case PASSED for this requirement
   - "partial"   = some tests passed, some failed
   - "uncovered" = no test cases executed

2. SCENARIO COVERAGE – which risk categories were exercised:
   - Were positive, negative, edge_case, and boundary scenarios tested?
   - For high-priority requirements, was there proportional test coverage?

For each requirement, provide:
  - total_tests / passed_tests / failed_tests
  - coverage_status: covered | partial | uncovered
  - validation_status: validated | failing | skipped

Compute aggregate metrics:
  - coverage_percentage    = (covered + partial) / total * 100
  - validation_percentage  = validated / total * 100
  - defect_density per requirement (failed_tests / total_tests)

Your output MUST be a single valid JSON object with exactly these keys:
{{
  "total_requirements": <int>,
  "covered_requirements": <int>,
  "validated_requirements": <int>,
  "coverage_percentage": <float>,
  "validation_percentage": <float>,
  "uncovered_requirements": ["REQ-XXX", ...],
  "failed_requirements": ["REQ-XXX", ...],
  "by_type": {{"functional": <int>, "non_functional": <int>, ...}},
  "by_priority": {{"high": <int>, "medium": <int>, "low": <int>}},
  "requirement_details": [
    {{
      "requirement_id": "REQ-001",
      "total_tests": <int>,
      "passed_tests": <int>,
      "failed_tests": <int>,
      "coverage_status": "covered|partial|uncovered",
      "validation_status": "validated|failing|skipped",
      "defect_density": <float>
    }}
  ],
  "coverage_gaps": ["REQ-005 has no negative test cases", ...]
}}

Output ONLY the JSON object. Do not include any explanation or markdown fences.""",
        expected_output=(
            "A single valid JSON object with post-execution coverage metrics. "
            "Required keys: total_requirements, covered_requirements, validated_requirements, "
            "coverage_percentage, validation_percentage, uncovered_requirements, "
            "failed_requirements, by_type, by_priority, requirement_details (array), "
            "coverage_gaps (array of strings describing gaps)."
        ),
        agent=agent,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 – Root Cause Analyzer
# ─────────────────────────────────────────────────────────────────────────────


def make_root_cause_task(
    agent: "Agent",
    execution_results_json: list[dict[str, Any]],
    test_cases_json: list[dict[str, Any]] | None = None,
    context_tasks: list["TaskType"] | None = None,
) -> "TaskType":
    """
    Build the root cause analysis task for failed / errored test cases.

    Analyzes failure patterns, groups similar failures, identifies probable
    root causes, and provides actionable remediation recommendations.

    Args:
        agent:                   The root_cause_analyzer CrewAI Agent.
        execution_results_json:  Full list of TestExecutionResult dicts.
        test_cases_json:         Optional list of TestCase dicts for context.
        context_tasks:           Optional list of preceding tasks to use as context.

    Returns:
        A configured ``crewai.Task`` instance.
    """
    _require_crewai()

    # Filter to only failed / error results
    failures = [
        r
        for r in execution_results_json
        if str(r.get("status", "")).lower() in ("failed", "error")
    ]
    failed_count = len(failures)
    total_count = len(execution_results_json)

    # Build an index of tc_id → test_case for context enrichment
    tc_index: dict[str, dict[str, Any]] = {}
    if test_cases_json:
        for tc in test_cases_json:
            tc_index[str(tc.get("id", "?"))] = tc

    # Enrich failure records with test case context
    enriched_failures: list[dict[str, Any]] = []
    for failure in failures:
        tc_id = str(failure.get("test_case_id", "?"))
        tc_info = tc_index.get(tc_id, {})
        enriched_failures.append(
            {
                "test_case_id": tc_id,
                "status": failure.get("status"),
                "actual_status_code": failure.get("actual_status_code"),
                "error_message": failure.get("error_message"),
                "actual_result": str(failure.get("actual_result", ""))[:300],
                "logs": failure.get("logs", [])[:5],
                # from test case
                "expected_status_code": tc_info.get("expected_status_code"),
                "api_endpoint": tc_info.get("api_endpoint"),
                "http_method": tc_info.get("http_method"),
                "category": tc_info.get("category"),
                "priority": tc_info.get("priority"),
                "requirement_id": tc_info.get("requirement_id"),
            }
        )

    failures_str = _safe_json(enriched_failures, max_items=30)

    no_failures_note = (
        "\nNote: No failures or errors were found in the execution results. "
        "Return an empty array [] as your output.\n"
        if failed_count == 0
        else ""
    )

    return Task(
        description=f"""You are the root cause analyst.

Execution summary:
  - Total test cases executed: {total_count}
  - Failed + Error cases     : {failed_count}
  - Success rate             : {round((total_count - failed_count) / total_count * 100, 1) if total_count > 0 else 0}%
{no_failures_note}
Failed / errored test cases (with context):
{failures_str}

Your job is to:

1. CLASSIFY each failure into one of these root cause categories:
   - authentication  : 401/403, missing/expired tokens
   - data            : invalid request body, schema mismatch, missing required field
   - logic           : unexpected business logic, wrong expected result in test
   - environment     : network error, DNS failure, service unavailable
   - network         : timeout, connection refused, SSL error
   - timeout         : response exceeded time limit
   - unknown         : cannot determine from available information

2. GROUP similar failures under shared root causes — many failures may stem
   from the same underlying issue (e.g., all 401 errors → same auth problem).

3. PRIORITIZE by severity:
   - critical : blocks all further testing (e.g., env unreachable)
   - high     : affects high-priority requirements
   - medium   : affects medium-priority or non-blocking requirements
   - low      : cosmetic or edge-case failures

4. PROVIDE specific, actionable remediation recommendations.

Your output MUST be a single valid JSON array (even if empty):
[
  {{
    "test_case_id": "TC-002",
    "failure_pattern": "HTTP 401 Unauthorized on all authenticated endpoints",
    "probable_cause": "Auth token missing or expired in test environment",
    "root_cause_category": "authentication|data|logic|environment|network|timeout|unknown",
    "recommendation": "Verify that TEST_AUTH_TOKEN env var is set and token is valid",
    "affected_tests": ["TC-002", "TC-007", "TC-012"],
    "severity": "critical|high|medium|low",
    "suggested_fix": "Set TEST_AUTH_TOKEN=<valid_token> before re-running tests"
  }}
]

Group failures with the same root cause into ONE entry with all affected_tests listed.
Output ONLY the JSON array. Do not include any explanation or markdown fences.""",
        expected_output=(
            "A valid JSON array of root cause analysis entries (may be empty if no failures). "
            "Each entry must have: test_case_id (representative failing test), "
            "failure_pattern, probable_cause, root_cause_category "
            "(authentication|data|logic|environment|network|timeout|unknown), "
            "recommendation, affected_tests (array of all TC IDs sharing this cause), "
            "severity (critical|high|medium|low), suggested_fix."
        ),
        agent=agent,
        context=context_tasks or [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 – Report Generator
# ─────────────────────────────────────────────────────────────────────────────


def make_report_generator_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
    execution_summary: dict[str, Any] | None = None,
    document_name: str = "uploaded document",
) -> "TaskType":
    """
    Build the final report generation task.

    This task consumes outputs from the coverage_analyzer and root_cause_analyzer
    tasks (via ``context_tasks``) and produces a comprehensive report suitable
    for both technical and non-technical stakeholders.

    Args:
        agent:             The report_generator CrewAI Agent.
        context_tasks:     List of preceding tasks (coverage + root cause tasks).
        execution_summary: Optional pre-computed ExecutionSummary dict to include
                           in the report metadata (total, passed, failed, etc.).
        document_name:     Name of the source document being tested.

    Returns:
        A configured ``crewai.Task`` instance.
    """
    _require_crewai()

    summary_str = ""
    if execution_summary:
        total = execution_summary.get("total", 0)
        passed = execution_summary.get("passed", 0)
        failed = execution_summary.get("failed", 0)
        skipped = execution_summary.get("skipped", 0)
        errors = execution_summary.get("errors", 0)
        pass_rate = execution_summary.get("pass_rate", 0.0)
        duration = execution_summary.get("duration_seconds", 0.0)

        summary_str = f"""
Known execution summary:
  Total    : {total}
  Passed   : {passed}
  Failed   : {failed}
  Skipped  : {skipped}
  Errors   : {errors}
  Pass rate: {pass_rate}%
  Duration : {duration}s
"""

    return Task(
        description=f"""You are the report generator. Your job is to produce a final, comprehensive
test execution report for the document: "{document_name}".
{summary_str}
You have access to two upstream task outputs via context:
  1. Coverage Analysis  (from coverage_analyzer task)
  2. Root Cause Analysis (from root_cause_analyzer task)

Use BOTH to produce a report that is:
  - Professional and clear for non-technical stakeholders (executive_summary)
  - Actionable and specific for engineers (recommendations + root_cause_analysis)
  - Complete with all metrics and traceability

Structure your report as follows:

EXECUTIVE SUMMARY (3–5 sentences):
  - What document was tested and how many requirements were found
  - How many test cases were generated and executed
  - Overall pass rate and coverage percentage
  - Top 1–2 critical issues that need immediate attention (if any)

RECOMMENDATIONS (ordered by priority):
  - Priority 1: Fix [specific issue] — affects [N] tests / [requirement]
  - Priority 2: ...
  - Each recommendation must reference specific requirement IDs or test IDs

RISK ITEMS:
  - Any high-priority requirements with failing tests
  - Any requirements with zero test coverage
  - Any critical root causes that block the entire test suite

Your output MUST be a single valid JSON object:
{{
  "coverage_percentage": <float — from coverage_analyzer output>,
  "coverage_analysis": {{...}},            // full coverage_analyzer JSON output
  "root_cause_analysis": [...],            // full root_cause_analyzer JSON output
  "executive_summary": "<3-5 sentence professional summary>",
  "recommendations": [
    "Priority 1: <specific actionable recommendation>",
    "Priority 2: ...",
    ...
  ],
  "risk_items": [
    "<risk description>",
    ...
  ],
  "generated_at": "<ISO 8601 UTC timestamp>",
  "total_test_cases": <int>,
  "pass_rate": <float>,
  "metrics": {{
    "total": <int>,
    "passed": <int>,
    "failed": <int>,
    "skipped": <int>,
    "errors": <int>,
    "duration_seconds": <float>,
    "coverage_percentage": <float>,
    "validation_percentage": <float>
  }}
}}

The "coverage_analysis" and "root_cause_analysis" fields MUST contain the COMPLETE
JSON outputs from the previous tasks, not summaries.

Output ONLY the JSON object. Do not include any explanation or markdown fences.""",
        expected_output=(
            "A single valid JSON report object with keys: "
            "coverage_percentage (float), coverage_analysis (full coverage object), "
            "root_cause_analysis (full root cause array), executive_summary (string), "
            "recommendations (string array, priority-ordered), risk_items (string array), "
            "generated_at (ISO 8601), total_test_cases (int), pass_rate (float), "
            "metrics (dict with total/passed/failed/skipped/errors/duration/coverage stats)."
        ),
        agent=agent,
        context=context_tasks,
    )
