"""Safe, append-only execution and agent activity records."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

_SENSITIVE_KEYS = {"authorization", "cookie", "password", "secret", "token", "api_key"}
_SOURCES = {"control_plane", "workflow", "worker", "generation", "triage", "reporting", "vision"}
_STATUSES = {
    "queued",
    "running",
    "passed",
    "failed",
    "errored",
    "cancelled",
    "info",
    "unavailable",
}

_VISION_PROGRESS = {
    "queued": ("queued", "Visual exploration queued.", frozenset()),
    "started": ("running", "Visual exploration started.", frozenset()),
    "state.captured": (
        "running",
        "Safe browser state was captured.",
        frozenset({"state_sequence", "hop"}),
    ),
    "candidate.requested": (
        "running",
        "Visual action candidates were requested.",
        frozenset({"state_sequence", "hop"}),
    ),
    "candidate.received": (
        "running",
        "Visual action candidates were received.",
        frozenset({"state_sequence", "candidate_count"}),
    ),
    "action.recorded": (
        "running",
        "Visual action candidate was recorded.",
        frozenset(
            {
                "state_sequence",
                "action_sequence",
                "action_kind",
                "confidence",
                "x",
                "y",
                "delta_y",
                "duration_ms",
            }
        ),
    ),
    "edge.proposed": (
        "running",
        "Visual trajectory candidate was proposed.",
        frozenset(
            {
                "state_sequence",
                "action_sequence",
                "action_kind",
                "confidence",
                "coordinate_available",
            }
        ),
    ),
    "edge.observed": (
        "running",
        "Visual trajectory candidate was observed.",
        frozenset({"state_sequence", "action_sequence", "outcome", "duration_ms", "url_change"}),
    ),
    "edge.failed": (
        "info",
        "Visual trajectory candidate was not observed.",
        frozenset({"state_sequence", "action_sequence", "outcome_code"}),
    ),
    "edge.terminal": (
        "info",
        "Visual trajectory candidate reached a terminal outcome.",
        frozenset({"state_sequence", "action_sequence", "outcome_code"}),
    ),
    "limit.reached": (
        "info",
        "Visual exploration reached a configured traversal limit.",
        frozenset({"state_count", "hop"}),
    ),
    "draft.handoff": (
        "info",
        "Generated-draft handoff was attempted.",
        frozenset({"outcome"}),
    ),
    "completed": (
        "info",
        "Visual exploration completed.",
        frozenset({"state_count", "action_count"}),
    ),
    "unavailable": ("unavailable", "Visual exploration is unavailable.", frozenset()),
}

for _stage, _summary in {
    "operation.prepared": "Browser operation evidence was prepared.",
    "operation.executing": "Browser operation was dispatched.",
    "operation.completed": "Browser operation completed.",
    "operation.failed": "Browser operation failed.",
    "operation.rejected": "Browser operation was rejected.",
    "operation.unknown": "Browser operation outcome is unknown.",
    "locator.verified": "Browser locator was verified.",
    "locator.unresolved": "Browser locator could not be verified.",
    "state.restore_started": "Browser state restoration started.",
    "state.restored": "Browser state restoration was verified.",
    "state.restore_failed": "Browser state restoration failed.",
    "handoff.ready": "Verified exploration evidence is ready for generation.",
    "handoff.unavailable": "Exploration handoff is unavailable.",
}.items():
    _VISION_PROGRESS[_stage] = (
        "info", _summary, frozenset({"operation_id", "operation_sequence", "purpose"}),
    )

_VISION_PROGRESS["handoff.unavailable"] = (
    "unavailable", "Exploration handoff is unavailable.", frozenset({"reason_code"}),
)


def validate_safe_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("activity metadata must be an object")
    for key, item in value.items():
        if any(part in key.lower() for part in _SENSITIVE_KEYS):
            raise ValueError("activity metadata contains a sensitive key")
        if isinstance(item, dict):
            validate_safe_metadata(item)
        elif isinstance(item, (list, tuple)):
            for child in item:
                if isinstance(child, dict):
                    validate_safe_metadata(child)
    return value


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    id: UUID
    tenant_id: str
    run_id: UUID | None
    correlation_id: UUID
    source: str
    stage: str
    status: str
    safe_summary: str
    metadata: dict[str, object]
    occurred_at: datetime
    visual_exploration_session_id: UUID | None = None
    progress_key: str | None = None

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        correlation_id: UUID,
        source: str,
        stage: str,
        status: str,
        safe_summary: str,
        occurred_at: datetime,
        run_id: UUID | None = None,
        visual_exploration_session_id: UUID | None = None,
        progress_key: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> "ActivityEvent":
        if source not in _SOURCES or status not in _STATUSES or not stage or len(stage) > 100:
            raise ValueError("activity source, stage, or status is invalid")
        if not safe_summary or len(safe_summary) > 1_000:
            raise ValueError("activity summary is invalid")
        return cls(
            uuid4(),
            tenant_id,
            run_id,
            correlation_id,
            source,
            stage,
            status,
            safe_summary,
            validate_safe_metadata(metadata or {}),
            occurred_at,
            visual_exploration_session_id,
            progress_key,
        )

    @classmethod
    def create_vision_progress(
        cls,
        *,
        tenant_id: str,
        correlation_id: UUID,
        visual_exploration_session_id: UUID,
        stage: str,
        progress_key: str,
        occurred_at: datetime,
        metadata: dict[str, object] | None = None,
    ) -> "ActivityEvent":
        """Create a closed, independently redaction-safe Vision progress event."""
        definition = _VISION_PROGRESS.get(stage)
        if definition is None or not progress_key or len(progress_key) > 200:
            raise ValueError("vision progress stage or key is invalid")
        status, safe_summary, allowed_keys = definition
        safe_metadata = metadata or {}
        if "reason_code" in safe_metadata and safe_metadata["reason_code"] not in {
            "handoff_branch_limit", "handoff_incomplete", "no_eligible_branches",
            "generation_request_unavailable",
        }:
            raise ValueError("vision progress reason is invalid")
        if set(safe_metadata) - allowed_keys:
            raise ValueError("vision progress metadata is not allow-listed")
        if "operation_id" in safe_metadata:
            UUID(str(safe_metadata["operation_id"]))
        if "purpose" in safe_metadata and safe_metadata["purpose"] not in {
            "setup", "explore", "restore", "replay",
        }:
            raise ValueError("vision progress purpose is invalid")
        if "operation_sequence" in safe_metadata and (
            type(safe_metadata["operation_sequence"]) is not int
            or not 1 <= safe_metadata["operation_sequence"] <= 100_000
        ):
            raise ValueError("vision progress sequence is invalid")
        for value in safe_metadata.values():
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError("vision progress metadata value is invalid")
        return cls.create(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            source="vision",
            stage=stage,
            status=status,
            safe_summary=safe_summary,
            occurred_at=occurred_at,
            visual_exploration_session_id=visual_exploration_session_id,
            progress_key=progress_key,
            metadata=safe_metadata,
        )
