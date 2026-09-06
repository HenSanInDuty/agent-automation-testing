"""Fail-safe execution of advisory triage through the language-model port."""

from dataclasses import dataclass
from json import dumps
from typing import Any

from auto_at.contracts.agent import AgentProposal, TriageResult
from auto_at.contracts.execution import TestExecutionResult

from agents.prompts.triage import TRIAGE_SYSTEM_PROMPT
from agents.shared.models import LanguageModel
from agents.shared.runtime import AgentRuntimeConfig, AgentStepGuard
from agents.triage.service import propose_failure_triage, validate_triage_output


@dataclass(frozen=True)
class TriageExecutionOutcome:
    status: str
    proposal: AgentProposal | None = None
    triage: TriageResult | None = None
    detail: str | None = None


async def execute_triage(
    result: TestExecutionResult,
    runtime: AgentRuntimeConfig,
    model: LanguageModel,
    fallback_model: LanguageModel | None = None,
) -> TriageExecutionOutcome:
    """Run bounded advisory triage. Any failure leaves the runner result untouched."""
    proposal = propose_failure_triage(result, runtime.evidence)
    guard = AgentStepGuard(runtime.guard)
    evidence_json = dumps(proposal.evidence, sort_keys=True, separators=(",", ":"))
    if not guard.allow_next_step(
        requested_tokens=runtime.guard.max_tokens, evidence_bytes=len(evidence_json.encode("utf-8"))
    ):
        return TriageExecutionOutcome(status="unavailable", detail="triage guard exhausted")

    response = await _invoke(model, evidence_json, runtime.guard.max_tokens)
    if (
        isinstance(response, Exception)
        and runtime.fallback is not None
        and fallback_model is not None
    ):
        response = await _invoke(fallback_model, evidence_json, runtime.guard.max_tokens)
    if isinstance(response, Exception):
        return TriageExecutionOutcome(status="unavailable", detail="model provider unavailable")

    try:
        triage = validate_triage_output(_content_from_response(response))
    except (TypeError, ValueError):
        return TriageExecutionOutcome(status="unavailable", detail="model returned invalid triage")
    proposal.evidence["triage"] = triage.model_dump(mode="json")
    return TriageExecutionOutcome(status="proposed", proposal=proposal, triage=triage)


async def _invoke(model: LanguageModel, evidence_json: str, max_tokens: int) -> Any | Exception:
    try:
        return await model.ainvoke(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": TRIAGE_SYSTEM_PROMPT,
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
