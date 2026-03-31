from __future__ import annotations

"""
tasks/execution_tasks.py
────────────────────────
CrewAI Task factory functions for the Execution crew (5 agents).

Sequential pipeline:
    make_execution_orchestrator_task  →  Plan execution order & timeouts
    make_env_adapter_task             →  Resolve environment config
    make_test_runner_task             →  Execute API test cases
    make_execution_logger_task        →  Aggregate logs & timing stats
    make_result_store_task            →  Consolidate final execution output

Each function accepts:
    agent          – crewai.Agent instance built by AgentFactory
    *input_data*   – stage-specific structured input (dicts / lists)
    context_tasks  – list of upstream crewai.Task objects whose outputs will
                     be made available to this task via context injection

Usage::

    from app.tasks.execution_tasks import (
        make_execution_orchestrator_task,
        make_env_adapter_task,
        make_test_runner_task,
        make_execution_logger_task,
        make_result_store_task,
    )
"""

import json
import logging
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

# ── Optional CrewAI import ────────────────────────────────────────────────────
try:
    from crewai import Task  # type: ignore[import-untyped]

    _CREWAI_AVAILABLE = True
except ImportError:
    Task = None  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False

if TYPE_CHECKING:
    from crewai import Agent  # type: ignore[import-untyped]
    from crewai import Task as TaskType  # type: ignore[import-untyped]


# ─────────────────────────────────────────────────────────────────────────────
# Guard helper
# ─────────────────────────────────────────────────────────────────────────────


def _require_crewai() -> None:
    if not _CREWAI_AVAILABLE or Task is None:
        raise ImportError(
            "crewai is not installed. "
            "On Linux/macOS run: uv add crewai\n"
            "On Windows use Docker or WSL2 for crew execution."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 – Execution Orchestrator
# ─────────────────────────────────────────────────────────────────────────────


def make_execution_orchestrator_task(
    agent: "Agent",
    test_cases_json: list[dict[str, Any]],
    execution_config: Optional[dict[str, Any]] = None,
) -> "TaskType":
    """
    Build the Execution Orchestrator task.

    The orchestrator receives the full list of test cases and produces
    an execution plan that specifies ordering, parallelisation groups,
    priority queue, and per-type timeout configuration.

    Args:
        agent:            CrewAI Agent for the execution_orchestrator role.
        test_cases_json:  List of test-case dicts from the TestCase crew.
        execution_config: Optional caller-supplied overrides (e.g. timeouts).

    Returns:
        crewai.Task ready to be added to the Execution crew.
    """
    _require_crewai()

    tc_count = len(test_cases_json)
    # Build a compact summary for the prompt – avoid overwhelming the context window
    tc_summary_items = []
    for tc in test_cases_json[:10]:
        tc_summary_items.append(
            {
                "id": tc.get("id", "?"),
                "title": tc.get("title", "")[:60],
                "test_type": tc.get("test_type", "api"),
                "category": tc.get("category", "positive"),
                "priority": tc.get("priority", "medium"),
                "requirement_id": tc.get("requirement_id", "?"),
            }
        )

    tc_summary = json.dumps(tc_summary_items, indent=2)
    config_str = json.dumps(execution_config or {}, indent=2)

    return Task(
        description=f"""You are the Execution Orchestrator. Your job is to create an optimal
execution plan for {tc_count} test case(s).

Test cases summary (first 10 shown):
{tc_summary}

Caller-supplied execution config overrides:
{config_str}

Produce a detailed execution plan that:
1. Groups test cases by dependency order — independent tests execute first.
2. Identifies sets of test cases safe to run in parallel (same target endpoint
   with no shared mutable state).
3. Prioritises high-priority test cases within each group.
4. Sets per-type timeout values (API tests, UI tests, integration tests).
5. Estimates total execution duration based on test count and avg latency.

Your output MUST be a single JSON object:
{{
  "execution_order": ["TC-001", "TC-003", "TC-002"],
  "parallel_groups": [["TC-001", "TC-003"], ["TC-002"]],
  "priority_queue": ["TC-HIGH-001", "TC-HIGH-002"],
  "timeout_config": {{
    "default_timeout_ms": 5000,
    "api_timeout_ms": 3000,
    "ui_timeout_ms": 10000,
    "integration_timeout_ms": 15000
  }},
  "total_estimated_duration_ms": 15000,
  "execution_mode": "sequential",
  "notes": ["High-priority tests scheduled first", "..."]
}}""",
        expected_output=(
            "A JSON execution-plan object with exactly these keys: "
            "execution_order (array of TC IDs in run order), "
            "parallel_groups (array of arrays), "
            "priority_queue (array of high-priority TC IDs), "
            "timeout_config (dict with default/api/ui/integration timeout_ms), "
            "total_estimated_duration_ms (int), "
            "execution_mode ('sequential' or 'parallel'), "
            "notes (array of strings)."
        ),
        agent=agent,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 – Environment Adapter
# ─────────────────────────────────────────────────────────────────────────────


def make_env_adapter_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
    environment: str = "default",
    test_cases_json: Optional[list[dict[str, Any]]] = None,
) -> "TaskType":
    """
    Build the Environment Adapter task.

    The env_adapter uses the ``config_loader`` tool to retrieve the resolved
    environment configuration, then validates that all test-case endpoints
    are reachable and substitutes placeholder URLs with the actual base_url.

    Args:
        agent:            CrewAI Agent for the env_adapter role.
        context_tasks:    Upstream tasks to pull context from
                          (execution_orchestrator task).
        environment:      Target environment name (default / staging / production).
        test_cases_json:  Test cases that need endpoint adaptation (optional summary).

    Returns:
        crewai.Task ready to be added to the Execution crew.
    """
    _require_crewai()

    tc_count = len(test_cases_json) if test_cases_json else 0

    # Collect unique endpoints for a connectivity-check hint
    endpoints: list[str] = []
    if test_cases_json:
        seen: set[str] = set()
        for tc in test_cases_json:
            ep = tc.get("api_endpoint")
            if ep and ep not in seen:
                endpoints.append(ep)
                seen.add(ep)
                if len(endpoints) >= 5:
                    break

    endpoints_str = json.dumps(endpoints)

    return Task(
        description=f"""You are the Environment Adapter for the '{environment}' test environment.

Your responsibilities:
1. Call the **config_loader** tool with environment='{environment}' to retrieve the
   resolved configuration (base_url, auth_headers, timeouts, etc.).
2. Validate that the base_url is set and reachable (attempt a HEAD / GET on the root
   path if possible, or report as 'assumed reachable' if connectivity checks are skipped).
3. Adapt the {tc_count} test case(s) for this environment:
   - Replace any placeholder base_url values (e.g. {{BASE_URL}} or http://localhost)
     with the resolved base_url.
   - Merge auth_headers into each test case's request headers.
4. Identify any test cases that must be skipped due to environment constraints
   (e.g. destructive tests disabled in production).
5. Report the final adapted state.

Sample endpoints to validate: {endpoints_str}

Your output MUST be a single JSON object:
{{
  "environment": "{environment}",
  "base_url": "https://api.example.com",
  "auth_type": "Bearer",
  "auth_headers": {{"Authorization": "Bearer <token>"}},
  "timeout_seconds": 30,
  "adapted_test_count": {tc_count},
  "skipped_tests": [],
  "skipped_reasons": {{}},
  "environment_ready": true,
  "connectivity_status": "reachable",
  "validation_notes": ["base_url resolved from TEST_BASE_URL env var", "..."]
}}""",
        expected_output=(
            "A JSON environment-adapter report with: environment (str), "
            "base_url (str | null), auth_type (str), auth_headers (dict), "
            "timeout_seconds (int), adapted_test_count (int), "
            "skipped_tests (array of TC IDs), skipped_reasons (dict TC→reason), "
            "environment_ready (bool), connectivity_status (str), "
            "validation_notes (array of strings)."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 – Test Runner
# ─────────────────────────────────────────────────────────────────────────────


def make_test_runner_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
    test_cases_json: list[dict[str, Any]],
) -> "TaskType":
    """
    Build the Test Runner task.

    The test_runner uses the ``api_runner`` tool to execute each test case
    as an HTTP request, then compares the actual response against expected
    criteria and records a pass/fail result.

    Args:
        agent:            CrewAI Agent for the test_runner role.
        context_tasks:    Upstream tasks (orchestrator + env_adapter) to pull
                          base_url and auth_headers from.
        test_cases_json:  Full list of test cases to execute.

    Returns:
        crewai.Task ready to be added to the Execution crew.
    """
    _require_crewai()

    tc_count = len(test_cases_json)
    # Show a representative sample in the prompt
    sample_count = min(3, tc_count)
    sample = json.dumps(test_cases_json[:sample_count], indent=2)
    remaining = tc_count - sample_count

    return Task(
        description=f"""You are the Test Runner. Execute {tc_count} API test case(s) using the
**api_runner** tool. Apply the base_url and auth_headers resolved by the
env_adapter (available in context).

For each test case:
1. Construct the full URL: base_url + api_endpoint.
2. Merge auth_headers with any test-case-specific request_headers.
3. Call the api_runner tool with the correct method, url, headers, body, and
   expected_status_code.
4. Compare actual_status_code vs expected_status_code:
   - Match → status = "passed"
   - Mismatch → status = "failed"
5. If the api_runner returns an error (network / timeout) → status = "error".
6. Record actual_result, duration_ms, actual_response, and execution logs.

Sample test cases (first {sample_count}):
{sample}
{"... and " + str(remaining) + " more test cases." if remaining > 0 else ""}

Your output MUST be a JSON array — one result object per test case:
[
  {{
    "test_case_id": "TC-001",
    "status": "passed",
    "duration_ms": 245.5,
    "actual_result": "HTTP 200 OK – user created successfully",
    "actual_status_code": 200,
    "actual_response": {{"id": 1, "username": "alice"}},
    "error_message": null,
    "timestamp": "2024-01-01T00:00:00Z",
    "logs": [
      "Sending POST /api/v1/users",
      "Received 200 OK in 245.5 ms",
      "Status code matches expected 200 → PASSED"
    ]
  }}
]""",
        expected_output=(
            "A JSON array of test execution result objects. "
            "Each object must have exactly: "
            "test_case_id (str), status (passed|failed|skipped|error), "
            "duration_ms (float), actual_result (str), "
            "actual_status_code (int|null), actual_response (dict|null), "
            "error_message (str|null), timestamp (ISO-8601 str), "
            "logs (array of strings). "
            "The array length must equal the number of test cases provided."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 4 – Execution Logger
# ─────────────────────────────────────────────────────────────────────────────


def make_execution_logger_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Build the Execution Logger task.

    The logger aggregates all raw test results from the test_runner,
    computes timing statistics, detects anomalies (unusually slow tests,
    repeated connection errors), and groups failures into patterns.

    Args:
        agent:         CrewAI Agent for the execution_logger role.
        context_tasks: Upstream tasks (test_runner + env_adapter).

    Returns:
        crewai.Task ready to be added to the Execution crew.
    """
    _require_crewai()

    return Task(
        description="""You are the Execution Logger. Process all test execution results
from the test_runner (available in context) and produce a structured, queryable
log summary.

Your tasks:
1. Aggregate all per-test logs into a unified chronological log stream.
2. Compute timing statistics across all test results:
   - min, max, average, and 95th-percentile (p95) duration_ms.
3. Detect anomalies:
   - Tests slower than 3× the average duration.
   - Tests with repeated connection or timeout errors.
   - Unusual HTTP status codes (5xx, unexpected 4xx patterns).
4. Group failures into recurring patterns:
   - Same error message or HTTP status code affecting multiple tests.
   - Endpoint-level failures (all tests for one API path failing).
5. Compute a per-status breakdown: total, passed, failed, skipped, errors.

Your output MUST be a single JSON object:
{
  "log_entries": [
    {
      "timestamp": "2024-01-01T00:00:00.000Z",
      "test_case_id": "TC-001",
      "level": "INFO",
      "message": "TC-001 PASSED in 245.5 ms",
      "metadata": {"status_code": 200, "duration_ms": 245.5}
    }
  ],
  "timing_stats": {
    "min_ms": 100.0,
    "max_ms": 5000.0,
    "avg_ms": 450.2,
    "p95_ms": 1200.0
  },
  "status_breakdown": {
    "total": 25,
    "passed": 20,
    "failed": 3,
    "skipped": 1,
    "errors": 1
  },
  "anomalies": [
    {"type": "slow_test", "test_case_id": "TC-010", "duration_ms": 4500.0,
     "threshold_ms": 1350.6, "message": "3× above average duration"}
  ],
  "failure_patterns": [
    {
      "pattern": "HTTP 401 Unauthorized",
      "affected_tests": ["TC-002", "TC-007"],
      "occurrence_count": 2,
      "probable_cause": "Auth token missing or expired"
    }
  ]
}""",
        expected_output=(
            "A JSON log-summary object with: log_entries (array), "
            "timing_stats (min_ms/max_ms/avg_ms/p95_ms), "
            "status_breakdown (total/passed/failed/skipped/errors), "
            "anomalies (array), failure_patterns (array with "
            "pattern/affected_tests/occurrence_count/probable_cause)."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 5 – Result Store
# ─────────────────────────────────────────────────────────────────────────────


def make_result_store_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Build the Result Store task.

    The result_store manager consolidates outputs from all upstream execution
    agents (orchestrator plan, env_adapter config, test_runner results,
    execution_logger stats) into the canonical ExecutionOutput format.
    This is the final output of the Execution crew, consumed by the Reporting crew.

    Args:
        agent:         CrewAI Agent for the result_store role.
        context_tasks: All upstream execution tasks.

    Returns:
        crewai.Task ready to be added to the Execution crew.
    """
    _require_crewai()

    return Task(
        description="""You are the Result Store Manager. Your job is to consolidate the outputs
from ALL upstream execution agents (available in context) into a single, canonical
ExecutionOutput document that will be consumed by the Reporting crew.

Collect and merge:
1. Execution plan      – from execution_orchestrator (timing config, execution mode)
2. Environment config  – from env_adapter (base_url, environment name, skipped tests)
3. Test results        – from test_runner (full array of TestExecutionResult objects)
4. Log summary         – from execution_logger (timing_stats, failure_patterns, anomalies)

Compute the final summary metrics:
  total    = count of all results
  passed   = count where status == "passed"
  failed   = count where status == "failed"
  skipped  = count where status == "skipped"
  errors   = count where status == "error"
  pass_rate = passed / total * 100 (rounded to 1 decimal)
  duration_seconds = sum of all duration_ms / 1000

Your output MUST be a single JSON object matching the ExecutionOutput schema:
{
  "results": [
    {
      "test_case_id": "TC-001",
      "status": "passed",
      "duration_ms": 245.5,
      "actual_result": "...",
      "actual_status_code": 200,
      "actual_response": {},
      "error_message": null,
      "timestamp": "2024-01-01T00:00:00Z",
      "logs": ["..."]
    }
  ],
  "summary": {
    "total": 25,
    "passed": 20,
    "failed": 3,
    "skipped": 1,
    "errors": 1,
    "pass_rate": 80.0,
    "duration_seconds": 45.2
  },
  "environment": "default",
  "timing_stats": {
    "min_ms": 100.0,
    "max_ms": 5000.0,
    "avg_ms": 450.2,
    "p95_ms": 1200.0
  },
  "failure_patterns": [
    {
      "pattern": "HTTP 401 Unauthorized",
      "affected_tests": ["TC-002"],
      "occurrence_count": 1
    }
  ],
  "execution_notes": [
    "Execution completed in sequential mode",
    "1 test skipped: environment constraint in production",
    "2 anomalies detected — see timing_stats"
  ]
}""",
        expected_output=(
            "A single JSON ExecutionOutput object — the canonical final output of the "
            "Execution crew — with: results (full array of TestExecutionResult objects), "
            "summary (total/passed/failed/skipped/errors/pass_rate/duration_seconds), "
            "environment (str), timing_stats, failure_patterns, execution_notes (array). "
            "This object will be passed directly to the Reporting crew."
        ),
        agent=agent,
        context=context_tasks,
    )
