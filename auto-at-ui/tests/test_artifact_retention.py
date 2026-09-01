from datetime import UTC, datetime, timedelta
from uuid import uuid4

from application.artifact_retention import ExpireArtifacts, ExpiryResult
from domain.entities import ArtifactRecord


class Repository:
    def __init__(self, items):
        self.items = items

    def list_expired(self, before, limit):
        return [item for item in self.items if item.retention_until <= before][:limit]

    def delete_expired(self, tenant_id, artifact_id):
        for item in list(self.items):
            if item.tenant_id == tenant_id and item.id == artifact_id:
                self.items.remove(item)
                return True
        return False


class Store:
    def __init__(self):
        self.deleted = []

    def delete(self, artifact):
        self.deleted.append(artifact.id)


def test_expiry_deletes_bytes_before_tenant_scoped_metadata() -> None:
    now = datetime.now(UTC)
    artifact = ArtifactRecord(
        uuid4(),
        "tenant-a",
        uuid4(),
        "trace",
        "s3://bucket/tenants/tenant-a/runs/x/artifacts/a",
        "a" * 64,
        1,
        retention_until=now - timedelta(seconds=1),
    )
    repository, store = Repository([artifact]), Store()
    assert ExpireArtifacts(repository, store).execute(now=now) == ExpiryResult(deleted=1, failed=0)
    assert store.deleted == [artifact.id] and repository.items == []
