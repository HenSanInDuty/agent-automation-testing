"""Pure lifecycle and scope rules for chronological Vision evidence."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from auto_at.contracts.vision import VisualOperation


class VisionImageAuthorizationRequired(RuntimeError):
    """Image delivery requires renewed authorization; no provider details escape."""


VISION_MODEL_FAILURE_REASONS = frozenset({
    "provider_not_configured", "provider_auth_failed", "provider_billing_required",
    "provider_rate_limited", "provider_model_unavailable", "provider_timeout",
    "provider_unavailable", "model_output_invalid", "model_unavailable",
})


def vision_model_failure_reason(reason: str | None) -> str:
    return reason if reason in VISION_MODEL_FAILURE_REASONS else "model_unavailable"


FINAL_OPERATION_STATUSES = frozenset({"completed", "failed", "unknown", "rejected"})
_TRANSITIONS = {
    "prepared": {"prepared", "executing", "failed", "unknown", "rejected"},
    # Executing records dispatch intent; the worker may still reject a stale target.
    "executing": FINAL_OPERATION_STATUSES,
}
_IDENTITY_FIELDS = (
    "id",
    "tenant_id",
    "project_id",
    "session_id",
    "sequence",
    "attempt",
    "parent_operation_id",
    "checkpoint_id",
    "edge_id",
    "state_id",
    "proposal_id",
    "purpose",
    "action_kind",
    "expected_parent_fingerprint",
    "started_at",
)


@dataclass(frozen=True)
class VisualSessionScope:
    tenant_id: str
    project_id: UUID
    session_id: UUID


@dataclass(frozen=True)
class VisualSessionLease:
    scope: VisualSessionScope
    owner: UUID
    fencing_token: int
    expires_at: datetime


def validate_operation_transition(old: VisualOperation, new: VisualOperation) -> None:
    if old == new:
        return
    if any(getattr(old, field) != getattr(new, field) for field in _IDENTITY_FIELDS):
        raise ValueError("operation identity is immutable")
    if new.status not in _TRANSITIONS.get(old.status, set()):
        raise ValueError("operation finalization is immutable or transition is invalid")
    for field in ("actual_before_frame_id", "actual_after_frame_id", "locator_id"):
        if getattr(old, field) is not None and getattr(old, field) != getattr(new, field):
            raise ValueError("operation evidence reference is immutable")
    if old.status == "executing" and old.locator_id != new.locator_id:
        raise ValueError("executing operation locator is immutable")
