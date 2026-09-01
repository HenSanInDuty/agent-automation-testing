import hashlib
from uuid import uuid4

import pytest
from config import Settings
from domain.entities import ArtifactRecord
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
