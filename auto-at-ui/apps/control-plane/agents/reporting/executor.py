"""Fail-safe bounded execution for an informational terminal run report."""

from dataclasses import dataclass
from json import dumps
from typing import Any

from auto_at.contracts.agent import RunReport, RunReportEvidenceBundle
from auto_at.contracts.execution import TestExecutionResult

from agents.reporting.service import validate_run_report_output
from agents.shared.models import LanguageModel
from agents.shared.runtime import AgentRuntimeConfig, AgentStepGuard


@dataclass(frozen=True)
class ReportingExecutionOutcome:
    status: str
    report: RunReport | None = None
    detail: str | None = None


async def execute_run_reporting(
    result: TestExecutionResult,
    evidence: RunReportEvidenceBundle,
    runtime: AgentRuntimeConfig,
    model: LanguageModel,
    fallback_model: LanguageModel | None = None,
) -> ReportingExecutionOutcome:
    """Summarize supplied facts only; no agent path can affect the run result."""
    guard = AgentStepGuard(runtime.guard)
    evidence_json = dumps(evidence.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    if not guard.allow_next_step(
        requested_tokens=runtime.guard.max_tokens,
        evidence_bytes=len(evidence_json.encode("utf-8")),
    ):
        return ReportingExecutionOutcome(status="unavailable", detail="reporting guard exhausted")
    response = await _invoke_reporting(model, evidence_json, runtime.guard.max_tokens)
    if (
        isinstance(response, Exception)
        and runtime.fallback is not None
        and fallback_model is not None
    ):
        response = await _invoke_reporting(fallback_model, evidence_json, runtime.guard.max_tokens)
    if isinstance(response, Exception):
        return ReportingExecutionOutcome(status="unavailable", detail="model provider unavailable")
    try:
        report = validate_run_report_output(_content_from_response(response), result)
    except (TypeError, ValueError):
        return ReportingExecutionOutcome(
            status="unavailable", detail="model returned invalid report"
        )
    return ReportingExecutionOutcome(status="completed", report=report)


async def _invoke_reporting(
    model: LanguageModel, evidence_json: str, max_tokens: int
) -> Any | Exception:
    try:
        return await model.ainvoke(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Create an informational report from supplied redacted evidence only. "
                            "Never claim a retry, fix, approval, or changed verdict. Preserve "
                            "deterministic_status exactly. Return only a JSON object with exactly "
                            "these fields: deterministic_status, headline, what_ran, observations, "
                            "failure, unverified_or_skipped, limitations. Each observation has "
                            "text and evidence_references. failure is null for passed/skipped "
                            "when no failure exists; for failed/errored it must have stage, "
                            "location, message, and evidence_references. Use 'Precise location "
                            "unavailable from permitted evidence.' when no safe location exists."
                        ),
                    },
                    {"role": "user", "content": evidence_json},
                ],
                "max_tokens": max_tokens,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        )
    except Exception as error:  # Provider failures are intentionally non-fatal to a run.
        return error


def _content_from_response(response: Any) -> str:
    if not isinstance(response, dict):
        raise TypeError("model response must be an OpenAI-compatible object")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("model response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise TypeError("model choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("model response has no textual message content")
    return message["content"]
