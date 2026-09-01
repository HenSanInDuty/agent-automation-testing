"""Idempotent, tenant-scoped expiry of durable artifact evidence."""

from dataclasses import dataclass
from datetime import UTC, datetime

from domain.ports import ArtifactRepository, VerifiedArtifactStore


@dataclass(frozen=True)
class ExpiryResult:
    deleted: int
    failed: int


class ExpireArtifacts:
    """Delete bytes before metadata; provider errors leave metadata retryable."""

    def __init__(self, artifacts: ArtifactRepository, store: VerifiedArtifactStore) -> None:
        self._artifacts = artifacts
        self._store = store

    def execute(self, *, now: datetime | None = None, limit: int = 100) -> ExpiryResult:
        cutoff = now or datetime.now(UTC)
        deleted = failed = 0
        for artifact in self._artifacts.list_expired(cutoff, limit):
            try:
                self._store.delete(artifact)
            except Exception:
                failed += 1
                continue
            if self._artifacts.delete_expired(artifact.tenant_id, artifact.id):
                deleted += 1
        return ExpiryResult(deleted=deleted, failed=failed)
