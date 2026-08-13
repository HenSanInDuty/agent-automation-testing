"""Strict validation for advisory terminal run reports."""

from auto_at.contracts.agent import RunReport
from auto_at.contracts.execution import TestExecutionResult
from pydantic import ValidationError


def validate_run_report_output(payload: str, result: TestExecutionResult) -> RunReport:
    """Accept a report only when it preserves the deterministic runner status."""
    try:
        report = RunReport.model_validate_json(payload)
    except ValidationError as error:
        raise ValueError("model returned an invalid run-report schema") from error
    if report.deterministic_status != result.status.value:
        raise ValueError("report must preserve the deterministic status")
    if result.status.value in {"failed", "errored"} and report.failure is None:
        raise ValueError("failed and errored reports require a failure section")
    return report
