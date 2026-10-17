"""One-shot, fail-safe execution of a visual action candidate."""

from base64 import b64encode
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx
from auto_at.contracts.vision import VisualAction

from agents.prompts.vision import VISION_BATCH_IMAGE_INSTRUCTION, VISION_SINGLE_IMAGE_INSTRUCTION
from agents.shared.models import LanguageModel
from agents.shared.runtime import AgentStepGuard, VisionPolicy
from agents.vision.diagnostics import (
    VisionProviderFailure,
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
    failure_reason: str | None = None


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
                    {"type": "text", "text": VISION_SINGLE_IMAGE_INSTRUCTION},
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
    guard: AgentStepGuard | None = None,
    image_url: str | None = None,
    requested_tokens: int = 1_000,
    image_delivery: AbstractAsyncContextManager[str | None] | None = None,
) -> VisualCandidateBatchOutcome:
    """Invoke once for a state; reply is advisory and cannot choose traversal order."""
    if (
        not policy.enabled or not policy.raw_screenshot_transfer_accepted
        or policy.raw_screenshot_transfer_provider != policy.provider
    ):
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
    if type(requested_tokens) is not int or not 1 <= requested_tokens <= 100_000:
        return VisualCandidateBatchOutcome(
            status="unavailable", detail="vision token cap is invalid"
        )
    guard = guard or AgentStepGuard(policy_to_step_guard(policy))
    if not guard.allow_next_step(requested_tokens=requested_tokens, evidence_bytes=len(screenshot)):
        return VisualCandidateBatchOutcome(status="unavailable", detail="vision guard exhausted")
    # Reserve the guard before any external image transfer. Context failures (such
    # as revoked live consent or expired Drive OAuth) belong to the orchestrator.
    async with image_delivery or nullcontext(image_url) as delivered_url:
        return await _invoke_candidate_batch(
            screenshot=screenshot, content_type=content_type, task_intent=task_intent,
            model=model, max_candidates=max_candidates, requested_tokens=requested_tokens,
            image_url=delivered_url,
        )


async def _invoke_candidate_batch(
    *, screenshot: bytes, content_type: str, task_intent: str, model: LanguageModel,
    max_candidates: int, requested_tokens: int, image_url: str | None,
) -> VisualCandidateBatchOutcome:
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
                    {"type": "text", "text": VISION_BATCH_IMAGE_INSTRUCTION},
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
            failure_reason=_failure_reason(error),
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
            failure_reason="model_output_invalid",
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
    if choices[0].get("finish_reason") not in (None, "stop"):
        raise VisualDiagnosticFailure(VisualDiagnosticCode.RESPONSE_INCOMPLETE)
    message = choices[0].get("message")
    if isinstance(message, dict) and message.get("refusal"):
        raise VisualDiagnosticFailure(VisualDiagnosticCode.RESPONSE_REFUSED)
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise VisualDiagnosticFailure(VisualDiagnosticCode.RESPONSE_MISSING_CONTENT)
    return message["content"]


def _provider_failure(error: Exception) -> VisualDiagnosticFailure:
    if isinstance(error, VisualDiagnosticFailure):
        return error
    if isinstance(error, VisionProviderFailure):
        return VisualDiagnosticFailure(
            VisualDiagnosticCode.PROVIDER_HTTP if error.provider_status
            else VisualDiagnosticCode.PROVIDER_TRANSPORT,
            provider_status=error.provider_status, provider_category=error.provider_category,
        )
    status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status, int):
        return VisualDiagnosticFailure(
            VisualDiagnosticCode.PROVIDER_HTTP, provider_status=status, provider_category="http"
        )
    category = (
        "timeout" if isinstance(error, (TimeoutError, httpx.TimeoutException)) else "transport"
    )
    return VisualDiagnosticFailure(
        VisualDiagnosticCode.PROVIDER_TRANSPORT, provider_category=category
    )


def _failure_reason(error: Exception) -> str:
    if isinstance(error, VisionProviderFailure):
        return error.reason
    if isinstance(error, VisualDiagnosticFailure):
        return "model_output_invalid"
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "provider_timeout"
    status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status, int):
        return VisionProviderFailure.from_status(status).reason
    return "provider_unavailable"


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
