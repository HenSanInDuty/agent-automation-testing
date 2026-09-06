"""Retry-safe retention cleanup for encrypted Vision diagnostics."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from domain.runs import AuditEvent


class VisionDebugRetentionRepository(Protocol):
    def list_expired_debug_evidence(self, before: datetime, limit: int) -> list[object]: ...

    def delete_expired_debug_evidence(self, tenant_id: str, evidence_id: UUID) -> bool: ...


class VisionDebugAuditRepository(Protocol):
    def append(self, event: AuditEvent) -> None: ...


@dataclass(frozen=True)
class VisionDebugExpiryResult:
    deleted: int
    failed: int
    overdue: int


class ExpireVisionDebugEvidence:
    def __init__(
        self,
        repository: VisionDebugRetentionRepository,
        audits: VisionDebugAuditRepository | None = None,
    ) -> None:
        self._repository = repository
        self._audits = audits

    def execute(self, *, now: datetime | None = None, limit: int = 100) -> VisionDebugExpiryResult:
        cutoff = now or datetime.now(UTC)
        deleted = failed = overdue = 0
        for evidence in self._repository.list_expired_debug_evidence(cutoff, limit):
            overdue += 1
            try:
                self._audit(evidence, "vision.debug_evidence_expiry_attempted")
                if self._repository.delete_expired_debug_evidence(evidence.tenant_id, evidence.id):
                    deleted += 1
                    self._audit(evidence, "vision.debug_evidence_deleted")
                else:
                    self._audit(evidence, "vision.debug_evidence_expiry_noop")
            except Exception:
                failed += 1
                self._audit(evidence, "vision.debug_evidence_expiry_failed")
        return VisionDebugExpiryResult(deleted, failed, overdue)

    def _audit(self, evidence: object, action: str) -> None:
        if self._audits is None:
            return
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=evidence.tenant_id,
                actor="vision-debug-retention",
                action=action,
                entity_type="vision_debug_evidence",
                entity_id=evidence.id,
                correlation_id=getattr(evidence, "correlation_id", uuid4()),
            )
        )
