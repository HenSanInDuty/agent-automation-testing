"""One-shot, fail-safe execution of a visual action candidate."""

from base64 import b64encode
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from auto_at.contracts.vision import VisualAction

from agents.shared.models import LanguageModel
from agents.shared.runtime import AgentStepGuard, VisionPolicy
from agents.vision.diagnostics import (
    VisualDiagnosticCapture,
    VisualDiagnosticCode,
    VisualDiagnosticFailure,
)
from agents.vision.service import (
    build_visual_action_prompt,
    build_visual_candidate_batch_prompt,
    validate_visual_action_output,
    validate_visual_candidate_batch_output,
)


@dataclass(frozen=True)
class VisualActionOutcome:
    status: str
    action: VisualAction | None = None
    latency_seconds: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class VisualCandidateBatchOutcome:
    status: str
    actions: list[VisualAction] | None = None
    latency_seconds: float | None = None
    detail: str | None = None
    diagnostic_code: VisualDiagnosticCode | None = None
    diagnostic_capture: VisualDiagnosticCapture | None = None


async def execute_visual_action(
    *,
    screenshot: bytes,
    content_type: str,
    task_intent: str,
    policy: VisionPolicy,
    model: LanguageModel,
    image_url: str | None = None,
    requested_tokens: int = 1_000,
) -> VisualActionOutcome:
    """Invoke exactly once; any failure remains advisory and unavailable."""
    if not policy.enabled or not policy.raw_screenshot_transfer_accepted:
        return VisualActionOutcome(status="unavailable", detail="vision policy is disabled")
    if len(screenshot) > policy.max_screenshot_bytes:
        return VisualActionOutcome(status="unavailable", detail="screenshot exceeds policy cap")
    if content_type not in {"image/png", "image/jpeg"}:
        return VisualActionOutcome(status="unavailable", detail="screenshot type is not allowed")
    guard = AgentStepGuard(policy_to_step_guard(policy))
    if not guard.allow_next_step(requested_tokens=requested_tokens, evidence_bytes=len(screenshot)):
        return VisualActionOutcome(status="unavailable", detail="vision guard exhausted")
    image_data_uri = image_url or (
        f"data:{content_type};base64,{b64encode(screenshot).decode('ascii')}"
    )
    payload = {
        "messages": [
            {"role": "system", "content": build_visual_action_prompt(task_intent)},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Return one candidate action for the supplied image."},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_uri},
                    },
                ],
            },
        ],
        "max_tokens": requested_tokens,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    started = perf_counter()
    try:
        response = await model.ainvoke(payload)
    except Exception:
        return VisualActionOutcome(
            status="unavailable",
            latency_seconds=perf_counter() - started,
            detail="vision model request failed",
        )
    try:
        action = validate_visual_action_output(_content_from_response(response))
    except Exception:
        return VisualActionOutcome(
            status="unavailable",
            latency_seconds=perf_counter() - started,
            detail="vision model returned an invalid action",
        )
    return VisualActionOutcome(
        status="completed", action=action, latency_seconds=perf_counter() - started
    )


async def execute_visual_candidate_batch(
    *,
    screenshot: bytes,
    content_type: str,
    task_intent: str,
    policy: VisionPolicy,
    model: LanguageModel,
    max_candidates: int,
    image_url: str | None = None,
    requested_tokens: int = 1_000,
) -> VisualCandidateBatchOutcome:
    """Invoke once for a state; reply is advisory and cannot choose traversal order."""
    if not policy.enabled or not policy.raw_screenshot_transfer_accepted:
        return VisualCandidateBatchOutcome(status="unavailable", detail="vision policy is disabled")
    if len(screenshot) > policy.max_screenshot_bytes:
        return VisualCandidateBatchOutcome(
            status="unavailable", detail="screenshot exceeds policy cap"
        )
    if content_type not in {"image/png", "image/jpeg"}:
        return VisualCandidateBatchOutcome(
            status="unavailable", detail="screenshot type is not allowed"
        )
    if max_candidates < 1 or max_candidates > 20:
        return VisualCandidateBatchOutcome(
            status="unavailable", detail="candidate batch cap is invalid"
        )
    image_data_uri = (
        image_url or f"data:{content_type};base64,{b64encode(screenshot).decode('ascii')}"
    )
    payload = {
        "messages": [
            {
                "role": "system",
                "content": build_visual_candidate_batch_prompt(task_intent, max_candidates),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Return candidate actions for this state."},
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                ],
            },
        ],
        "max_tokens": requested_tokens,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    started = perf_counter()
    try:
        response = await model.ainvoke(payload)
    except Exception as error:
        failure = _provider_failure(error)
        return VisualCandidateBatchOutcome(
            status="unavailable",
            latency_seconds=perf_counter() - started,
            detail="vision model returned an invalid candidate batch",
            diagnostic_code=failure.code,
            diagnostic_capture=_capture_for_failure(failure),
        )
    try:
        content = _content_from_response(response)
        actions = validate_visual_candidate_batch_output(
            content, max_candidates
        )
    except VisualDiagnosticFailure as failure:
        return VisualCandidateBatchOutcome(
            status="unavailable",
            latency_seconds=perf_counter() - started,
            detail="vision model returned an invalid candidate batch",
            diagnostic_code=failure.code,
            diagnostic_capture=_capture_for_failure(
                failure, locals().get("content")
            ),
        )
    return VisualCandidateBatchOutcome(
        status="completed", actions=actions, latency_seconds=perf_counter() - started
    )


def policy_to_step_guard(policy: VisionPolicy):
    """Map vision's independent caps to the shared bounded-step guard."""
    from agents.shared.runtime import StepGuardPolicy

    return StepGuardPolicy(
        max_tokens=100_000,
        max_steps_per_run=policy.max_steps,
        max_evidence_bytes_per_step=policy.max_screenshot_bytes,
        max_concurrency=1,
    )


def _content_from_response(response: Any) -> str:
    if not isinstance(response, dict):
        raise VisualDiagnosticFailure(VisualDiagnosticCode.RESPONSE_NOT_OBJECT)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise VisualDiagnosticFailure(VisualDiagnosticCode.RESPONSE_MISSING_CHOICES)
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise VisualDiagnosticFailure(VisualDiagnosticCode.RESPONSE_MISSING_CONTENT)
    return message["content"]


def _provider_failure(error: Exception) -> VisualDiagnosticFailure:
    status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status, int):
        return VisualDiagnosticFailure(
            VisualDiagnosticCode.PROVIDER_HTTP, provider_status=status, provider_category="http"
        )
    category = "timeout" if isinstance(error, TimeoutError) else "transport"
    return VisualDiagnosticFailure(
        VisualDiagnosticCode.PROVIDER_TRANSPORT, provider_category=category
    )


def _capture_for_failure(
    failure: VisualDiagnosticFailure, content: str | None = None
) -> VisualDiagnosticCapture:
    try:
        return VisualDiagnosticCapture.from_content(
            content,
            provider_status=failure.provider_status,
            provider_category=failure.provider_category,
        )
    except VisualDiagnosticFailure:
        # Diagnostics must never turn an unavailable advisory result into an error.
        return VisualDiagnosticCapture(
            None, None, failure.provider_status, failure.provider_category
        )
