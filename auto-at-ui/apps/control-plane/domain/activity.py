"""Safe, append-only execution and agent activity records."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

_SENSITIVE_KEYS = {"authorization", "cookie", "password", "secret", "token", "api_key"}
_SOURCES = {"control_plane", "workflow", "worker", "generation", "triage", "reporting"}
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
        )
