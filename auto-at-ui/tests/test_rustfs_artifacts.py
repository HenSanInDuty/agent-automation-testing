import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from config import Settings
from domain.entities import ArtifactRecord, VisualReplayFrameRecord
from infrastructure.artifacts.rustfs import ArtifactStorageError, RustFSArtifactStore


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.bucket_created = False

    def head_bucket(self, **_kwargs):
        if not self.bucket_created:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, **_kwargs):
        self.bucket_created = True

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        self.objects[(Bucket, Key)] = {
            "Body": Body,
            "ContentType": ContentType,
            "Metadata": Metadata,
        }

    def head_object(self, Bucket, Key):
        item = self.objects[(Bucket, Key)]
        return {"ContentLength": len(item["Body"]), "Metadata": item["Metadata"]}

    def get_object(self, Bucket, Key):
        from io import BytesIO

        return {"Body": BytesIO(self.objects[(Bucket, Key)]["Body"])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def list_objects_v2(self, Bucket, Prefix):
        return {
            "Contents": [
                {"Key": key}
                for bucket, key in self.objects
                if bucket == Bucket and key.startswith(Prefix)
            ]
        }


def store(client: FakeS3) -> RustFSArtifactStore:
    return RustFSArtifactStore(Settings(rustfs_bucket="test-artifacts"), client=client)


def record(uri: str, content: bytes, *, tenant: str = "tenant-a") -> ArtifactRecord:
    return ArtifactRecord(
        uuid4(),
        tenant,
        uuid4(),
        "runner-log",
        uri,
        hashlib.sha256(content).hexdigest(),
        len(content),
    )


def test_rustfs_uses_path_style_tenant_scoped_keys_and_verifies_reads() -> None:
    client = FakeS3()
    target = record(
        "s3://test-artifacts/tenants/tenant-a/runs/run-a/artifacts/runner-log-a.jsonl", b"safe"
    )
    # Align the trusted URI with the generated record's actual run identity.
    target = ArtifactRecord(
        **{
            **target.__dict__,
            "uri": f"s3://test-artifacts/tenants/tenant-a/runs/{target.run_id}/artifacts/runner-log-a.jsonl",
        }
    )
    uri = store(client).put_verified(
        target.uri.split("/", 3)[3], b"safe", target.checksum, "application/x-ndjson"
    )

    assert uri == target.uri
    assert store(client).read_verified_bytes(target, 10) == b"safe"
    assert store(client).list_keys(target.tenant_id, target.run_id) == [target.uri.split("/", 3)[3]]


def test_rustfs_rejects_checksum_mismatch_and_cross_tenant_uri() -> None:
    client = FakeS3()
    target = record("s3://test-artifacts/tenants/other/runs/x/artifacts/log", b"safe")

    with pytest.raises(ValueError, match="checksum"):
        store(client).put_verified("tenants/tenant-a/runs/x/artifacts/log", b"safe", "0" * 64, None)
    with pytest.raises(ValueError, match="URI"):
        store(client).read_verified_bytes(target, 10)


def test_rustfs_maps_provider_errors_without_provider_detail() -> None:
    class Broken(FakeS3):
        def put_object(self, **_kwargs):
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")

    target = record("s3://test-artifacts/tenants/tenant-a/runs/x/artifacts/log", b"safe")
    with pytest.raises(ArtifactStorageError, match="upload failed"):
        store(Broken()).put_verified(
            "tenants/tenant-a/runs/x/artifacts/log", b"safe", target.checksum, None
        )


def test_rustfs_writes_only_verified_tenant_scoped_replay_frames() -> None:
    content = b"\x89PNG\r\n\x1a\nvisual-replay"
    session_id, state_id = uuid4(), uuid4()
    frame = VisualReplayFrameRecord(
        id=uuid4(), tenant_id="tenant-a", session_id=session_id, state_id=state_id,
        sequence=1,
        storage_key=(
            f"tenants/tenant-a/vision-explorations/{session_id}/states/{state_id}.png"
        ),
        checksum=hashlib.sha256(content).hexdigest(), size=len(content), content_type="image/png",
        captured_at=datetime.now(UTC),
    )
    client = FakeS3()

    store(client).write_replay_frame(frame, content)

    assert ("test-artifacts", frame.storage_key) in client.objects
    invalid = VisualReplayFrameRecord(**{**frame.__dict__, "storage_key": "tenants/other/x"})
    with pytest.raises(ValueError, match="storage key"):
        store(client).write_replay_frame(invalid, content)


def test_rustfs_replay_write_is_idempotent_and_never_overwrites_conflicting_bytes() -> None:
    content = b"\x89PNG\r\n\x1a\nvisual-replay"
    session_id, state_id = uuid4(), uuid4()
    frame = VisualReplayFrameRecord(
        id=uuid4(), tenant_id="tenant-a", session_id=session_id, state_id=state_id,
        sequence=1,
        storage_key=f"tenants/tenant-a/vision-explorations/{session_id}/states/{state_id}.png",
        checksum=hashlib.sha256(content).hexdigest(), size=len(content), content_type="image/png",
        captured_at=datetime.now(UTC),
    )
    client = FakeS3()
    artifact_store = store(client)

    artifact_store.write_replay_frame(frame, content)
    artifact_store.write_replay_frame(frame, content)
    conflicting = b"\x89PNG\r\n\x1a\ndifferent"
    conflicting_frame = VisualReplayFrameRecord(
        **{
            **frame.__dict__,
            "checksum": hashlib.sha256(conflicting).hexdigest(),
            "size": len(conflicting),
        }
    )

    with pytest.raises(ArtifactStorageError, match="verification failed"):
        artifact_store.write_replay_frame(conflicting_frame, conflicting)
    assert client.objects[("test-artifacts", frame.storage_key)]["Body"] == content
