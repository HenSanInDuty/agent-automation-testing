"""Pure local bridge scope, deadline and lifecycle guards."""

from dataclasses import dataclass
from datetime import datetime

from auto_at.contracts.codex_bridge import (
    CodexBridgeRequest,
    CodexBridgeResponse,
    CodexConsentSnapshot,
    CodexDomObservation,
    CodexOutput,
    CodexUsage,
    FailureCode,
    canonical_bytes,
    content_hash,
)

CLI_VERSION = "0.164.0"


def input_snapshot(policy) -> CodexConsentSnapshot:
    if policy.provider != "codex_cli" or policy.codex is None:
        raise ValueError("Codex input policy required")
    return CodexConsentSnapshot(
        **policy.codex.model_dump(),
        raw_screenshot_transfer_accepted=policy.raw_screenshot_transfer_accepted,
        raw_screenshot_transfer_provider=policy.raw_screenshot_transfer_provider,
    )


def input_fingerprint(policy) -> str | None:
    return content_hash(input_snapshot(policy)) if policy.provider == "codex_cli" else None


@dataclass(frozen=True)
class BridgeProcessResult:
    output: CodexOutput | None = None
    failure_code: FailureCode | None = None
    actual_model: str | None = None
    usage: CodexUsage | None = None

TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled", "expired"})
_TRANSITIONS = {
    "queued": {"claimed", "failed", "cancelled", "expired"},
    "claimed": {"running", "failed", "cancelled", "expired"},
    "running": TERMINAL_JOB_STATUSES,
}
_IDENTITY_FIELDS = (
    "job_id", "bridge_id", "tenant_id", "project_id", "session_id", "correlation_id",
    "fencing_token", "request_sequence", "observation_id", "snapshot_id", "state_fingerprint",
    "stage",
)


def validate_job_transition(old: str, new: str) -> None:
    if new not in _TRANSITIONS.get(old, set()):
        raise ValueError("invalid or terminal bridge job transition")


def validate_request_time(request: CodexBridgeRequest, now: datetime) -> None:
    if now.tzinfo is None or not request.created_at <= now < request.deadline:
        raise ValueError("bridge request is future-dated or expired")


def validate_observation(request: CodexBridgeRequest, observation: CodexDomObservation) -> None:
    for field in ("tenant_id", "project_id", "session_id", "fencing_token", "observation_id",
                  "snapshot_id", "state_fingerprint"):
        if getattr(request, field) != getattr(observation, field):
            raise ValueError("bridge observation scope mismatch")
    if observation.captured_at > request.created_at:
        raise ValueError("observation is future-dated")
    if len(observation.elements) > request.consent.max_dom_elements:
        raise ValueError("observation exceeds consent element limit")
    if (request.dom_element_count is not None
            and request.dom_element_count != len(observation.elements)):
        raise ValueError("observation element count mismatch")
    if (content_hash(observation) != request.inputs.dom_sha256
            or len(canonical_bytes(observation)) != request.inputs.dom_bytes):
        raise ValueError("observation input hash or length mismatch")


def validate_response(
    request: CodexBridgeRequest, response: CodexBridgeResponse, *, now: datetime,
) -> None:
    validate_request_time(request, now)
    if any(getattr(request, name) != getattr(response, name) for name in _IDENTITY_FIELDS):
        raise ValueError("bridge response identity mismatch")
    if response.request_hash != content_hash(request):
        raise ValueError("bridge response request hash mismatch")
    if not request.created_at <= response.started_at <= response.completed_at <= now:
        raise ValueError("bridge response time mismatch")
    if response.actual_model is not None and response.actual_model != request.model:
        raise ValueError("bridge response model mismatch")
    if response.output and len(canonical_bytes(response.output)) > request.max_output_bytes:
        raise ValueError("bridge response output byte limit exceeded")
    if response.output and response.output.outcome == "candidates":
        if len(response.output.candidates) > request.candidate_limit:
            raise ValueError("bridge response candidate limit exceeded")


def validate_job_update(old, new) -> None:
    """Identity stays fixed; repositories must compare under their transaction lock."""
    if old == new:
        return
    immutable = (*_IDENTITY_FIELDS, "request_hash", "deadline", "created_at",
                 "dom_sha256", "dom_element_count")
    if any(getattr(old, name) != getattr(new, name) for name in immutable):
        raise ValueError("bridge job identity is immutable")
    validate_job_transition(old.status, new.status)
    if new.updated_at < old.updated_at:
        raise ValueError("bridge job update time cannot go backwards")
