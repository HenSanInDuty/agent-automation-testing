"""
tools/api_test_runner.py
────────────────────────
Pure-Python API test executor. Loops over each ``executable=True`` test
case in the input, sends the HTTP request via
:func:`app.tools.api_runner.run_api_request`, and assembles a
:class:`~app.schemas.pipeline_io.ExecutionOutput`.

Cases with ``executable=False`` are recorded as ``status="skipped"``
with the ``skip_reason`` preserved — they still appear in
``ExecutionOutput.results`` so the report verifier sees count > 0.

This module never calls an LLM — output is deterministic.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urlsplit

from app.schemas.pipeline_io import (
    ExecutionOutput,
    ExecutionStatus,
    ExecutionSummary,
    FailurePattern,
    TestExecutionResult,
    TimingStats,
)
from app.tools.api_runner import run_api_request

logger = logging.getLogger(__name__)

# Tolerate a leading list bullet (e.g. "- Base URL: …"), mirroring the
# validator's pattern so document scraping never diverges from parsing.
_RE_BASE_URL = re.compile(r"(?im)^\s*[-*]?\s*Base\s*URL\s*[:=]\s*(\S+)")


def execute_test_cases(
    test_cases: list[dict[str, Any]],
    document_content: str = "",
    base_url_override: Optional[str] = None,
    default_timeout: int = 15,
) -> ExecutionOutput:
    """Execute every executable case and aggregate results.

    Args:
        test_cases:         List of TestCase dicts (already classified —
                            each has ``executable`` and ``skip_reason``).
        document_content:   Raw markdown — used to recover ``Base URL`` if
                            ``base_url_override`` is not provided.
        base_url_override:  Optional override; takes precedence over the
                            Base URL declared in the spec body.
        default_timeout:    Per-request timeout in seconds.

    Returns:
        :class:`ExecutionOutput` model — call ``.model_dump()`` for
        storage by the DAG runner.
    """
    base_url = (base_url_override or _extract_base_url(document_content) or "").rstrip("/")
    results: list[TestExecutionResult] = []
    durations: list[float] = []
    notes: list[str] = []

    runnable = 0
    skipped = 0
    passed = 0
    failed = 0
    errors = 0
    skipped_reasons: dict[str, int] = {}

    if not base_url:
        notes.append(
            "No Base URL configured — all executable cases will be skipped."
        )

    # Stateful chaining: run cases so each producer (a create with ``extract``)
    # precedes its consumers, capture values from responses into ``context``, and
    # substitute ``{var}`` placeholders in dependent endpoints at run time.
    ordered_cases = _order_by_dependencies(test_cases)
    context: dict[str, str] = {}

    for tc in ordered_cases:
        if not isinstance(tc, dict):
            continue

        tc_id = str(tc.get("id") or "TC-?")
        executable = bool(tc.get("executable"))
        skip_reason = tc.get("skip_reason") or None
        obligation_ids = [
            str(o) for o in (tc.get("obligation_ids") or []) if isinstance(o, (str, int))
        ]

        if not executable or not base_url:
            reason = skip_reason or ("No Base URL configured" if not base_url else "executable=false")
            skipped += 1
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            results.append(
                TestExecutionResult(
                    test_case_id=tc_id,
                    status=ExecutionStatus.SKIPPED,
                    duration_ms=0.0,
                    actual_result=f"Skipped: {reason}",
                    skip_reason=reason,
                    obligation_ids=obligation_ids,
                )
            )
            continue

        # Resolve any {var} placeholders from previously captured values. A
        # missing value means the producer case failed or returned no id —
        # skip rather than send a literal placeholder to the server.
        endpoint, missing = _resolve_placeholders(
            str(tc.get("api_endpoint") or ""), context
        )
        if missing:
            reason = f"Unresolved chained value(s): {', '.join(sorted(set(missing)))}"
            skipped += 1
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            results.append(
                TestExecutionResult(
                    test_case_id=tc_id,
                    status=ExecutionStatus.SKIPPED,
                    duration_ms=0.0,
                    actual_result=f"Skipped: {reason}",
                    skip_reason=reason,
                    obligation_ids=obligation_ids,
                )
            )
            continue

        runnable += 1

        method = str(tc.get("http_method") or "GET").upper()
        url = _build_url(base_url, endpoint)
        headers = tc.get("request_headers") or None
        body = tc.get("request_body")
        expected_status = tc.get("expected_status_code")

        runner_result = run_api_request(
            url=url,
            method=method,
            headers=headers if isinstance(headers, dict) else None,
            body=body if isinstance(body, (dict, list, str)) else None,
            timeout=default_timeout,
            expected_status=int(expected_status) if expected_status is not None else None,
        )

        actual_code = runner_result.get("status_code")
        runner_error = runner_result.get("error")
        duration_ms = float(runner_result.get("duration_ms") or 0.0)
        durations.append(duration_ms)

        if runner_error and actual_code is None:
            status = ExecutionStatus.ERROR
            errors += 1
            actual_result = f"Network error: {runner_error}"
        elif runner_result.get("success"):
            status = ExecutionStatus.PASSED
            passed += 1
            actual_result = f"HTTP {actual_code} matches expected"
        else:
            status = ExecutionStatus.FAILED
            failed += 1
            actual_result = (
                f"HTTP {actual_code} differs from expected "
                f"{expected_status}"
            )

        actual_body = runner_result.get("body")

        # Capture chained values (e.g. a created resource id) for later cases.
        extract = tc.get("extract")
        if isinstance(extract, dict) and isinstance(actual_body, dict):
            for var, field in extract.items():
                if isinstance(field, str) and field in actual_body:
                    context[str(var)] = str(actual_body[field])

        if actual_body is not None and not isinstance(actual_body, dict):
            # Wrap non-dict bodies so the schema accepts them
            actual_body = {"raw": actual_body}

        results.append(
            TestExecutionResult(
                test_case_id=tc_id,
                status=status,
                duration_ms=round(duration_ms, 2),
                actual_result=actual_result,
                actual_status_code=actual_code,
                actual_response=actual_body if isinstance(actual_body, dict) else None,
                error_message=runner_error,
                logs=[f"{method} {url} → {actual_code if actual_code is not None else 'ERR'}"],
                obligation_ids=obligation_ids,
            )
        )

    summary = ExecutionSummary(
        total=len(results),
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration_seconds=round(sum(durations) / 1000.0, 3),
        runnable_count=runnable,
        skipped_count=skipped,
        skipped_reasons=skipped_reasons,
    )

    timing = _timing_stats(durations)
    failure_patterns = _failure_patterns(results)

    return ExecutionOutput(
        results=results,
        summary=summary,
        environment="default",
        timing_stats=timing,
        failure_patterns=failure_patterns,
        execution_notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _resolve_placeholders(
    text: str, context: dict[str, str]
) -> tuple[str, list[str]]:
    """Substitute ``{var}`` tokens from *context*; report any unresolved names."""
    missing: list[str] = []

    def _repl(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key in context:
            return str(context[key])
        missing.append(key)
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_repl, text or ""), missing


def _order_by_dependencies(
    test_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stable topological order so every ``depends_on`` producer runs first.

    Cases without dependencies keep their original order; a dependent is moved
    after the cases it needs. Cycles and unknown dependency ids are tolerated
    (the offending edge is simply ignored) so a malformed plan never deadlocks.
    """
    by_id: dict[str, dict[str, Any]] = {
        str(tc.get("id")): tc for tc in test_cases if isinstance(tc, dict)
    }
    ordered: list[dict[str, Any]] = []
    visited: set[str] = set()
    in_progress: set[str] = set()

    def _visit(tc: dict[str, Any]) -> None:
        tid = str(tc.get("id"))
        if tid in visited or tid in in_progress:
            return
        in_progress.add(tid)
        for dep in tc.get("depends_on") or []:
            dep_tc = by_id.get(str(dep))
            if dep_tc is not None:
                _visit(dep_tc)
        in_progress.discard(tid)
        visited.add(tid)
        ordered.append(tc)

    for tc in test_cases:
        if isinstance(tc, dict):
            _visit(tc)
        else:
            ordered.append(tc)
    return ordered


def _extract_base_url(text: str) -> str:
    m = _RE_BASE_URL.search(text or "")
    if not m:
        return ""
    return m.group(1).strip().strip("`").rstrip(".,;:")


def _build_url(base_url: str, endpoint_path: str) -> str:
    """Join base URL + endpoint path, tolerating either one carrying the slash."""
    if not endpoint_path:
        return base_url
    # If the endpoint already includes a scheme, prefer it as-is.
    if urlsplit(endpoint_path).scheme:
        return endpoint_path
    return base_url.rstrip("/") + "/" + endpoint_path.lstrip("/")


def _timing_stats(durations: list[float]) -> TimingStats:
    if not durations:
        return TimingStats()
    sorted_d = sorted(durations)
    n = len(sorted_d)
    p95_idx = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
    return TimingStats(
        min_ms=round(sorted_d[0], 2),
        max_ms=round(sorted_d[-1], 2),
        avg_ms=round(sum(sorted_d) / n, 2),
        p95_ms=round(sorted_d[p95_idx], 2),
    )


def _failure_patterns(results: list[TestExecutionResult]) -> list[FailurePattern]:
    """Group failed / error results by a short pattern string."""
    buckets: dict[str, list[str]] = {}
    for r in results:
        if r.status not in (ExecutionStatus.FAILED, ExecutionStatus.ERROR):
            continue
        key = _pattern_key(r)
        buckets.setdefault(key, []).append(r.test_case_id)
    return [
        FailurePattern(
            pattern=key,
            affected_tests=ids,
            occurrence_count=len(ids),
        )
        for key, ids in buckets.items()
    ]


def _pattern_key(r: TestExecutionResult) -> str:
    if r.status == ExecutionStatus.ERROR:
        msg = (r.error_message or "").split(":", 1)[0] or "error"
        return f"network/{msg[:40]}"
    return f"status-mismatch/{r.actual_status_code}"
