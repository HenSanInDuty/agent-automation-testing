"""Checksum-verified, tenant-scoped RustFS object storage adapter."""

import hashlib
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from config import Settings
from domain.entities import ArtifactRecord


class ArtifactStorageError(RuntimeError):
    """Safe storage failure: never surface provider diagnostics to callers."""


class RustFSArtifactStore:
    def __init__(self, settings: Settings, client=None) -> None:
        self._settings = settings
        self._bucket = settings.rustfs_bucket
        self._client = client or boto3.client(
            "s3",
            endpoint_url=settings.rustfs_endpoint,
            aws_access_key_id=settings.rustfs_access_key,
            aws_secret_access_key=settings.rustfs_secret_key,
            region_name=settings.rustfs_region,
            use_ssl=settings.rustfs_secure,
            config=Config(
                s3={"addressing_style": "path" if settings.rustfs_path_style else "virtual"}
            ),
        )
        self._bucket_ready = client is not None

    def put_verified(
        self, key: str, content: bytes, checksum: str, content_type: str | None
    ) -> str:
        self._validate_key(key)
        if hashlib.sha256(content).hexdigest() != checksum:
            raise ValueError("artifact checksum verification failed")
        try:
            self._ensure_bucket()
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type or "application/octet-stream",
                Metadata={"sha256": checksum},
            )
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError, KeyError) as error:
            raise ArtifactStorageError("artifact upload failed") from error
        if (
            head.get("ContentLength") != len(content)
            or head.get("Metadata", {}).get("sha256") != checksum
        ):
            raise ArtifactStorageError("artifact upload verification failed")
        return f"s3://{self._bucket}/{key}"

    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes:
        key = self._key_for_artifact(artifact)
        if artifact.size > max_bytes:
            raise ValueError("artifact exceeds the configured raw-byte cap")
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
            if (
                head.get("ContentLength") != artifact.size
                or head.get("Metadata", {}).get("sha256") != artifact.checksum
            ):
                raise ValueError("artifact checksum verification failed")
            content = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError, KeyError) as error:
            raise ArtifactStorageError("artifact read failed") from error
        if (
            len(content) != artifact.size
            or hashlib.sha256(content).hexdigest() != artifact.checksum
        ):
            raise ValueError("artifact checksum verification failed")
        return content

    def delete(self, artifact: ArtifactRecord) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=self._key_for_artifact(artifact))
        except (BotoCoreError, ClientError) as error:
            raise ArtifactStorageError("artifact deletion failed") from error

    def list_keys(self, tenant_id: str, run_id) -> list[str]:
        prefix = f"tenants/{tenant_id}/runs/{run_id}/"
        try:
            response = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        except (BotoCoreError, ClientError) as error:
            raise ArtifactStorageError("artifact listing failed") from error
        return sorted(
            item["Key"] for item in response.get("Contents", []) if isinstance(item.get("Key"), str)
        )

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket"}:
                raise
            self._client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True

    def _key_for_artifact(self, artifact: ArtifactRecord) -> str:
        parsed = urlparse(artifact.uri)
        if parsed.scheme != "s3" or parsed.netloc != self._bucket:
            raise ValueError("artifact URI is invalid")
        key = parsed.path.lstrip("/")
        expected = f"tenants/{artifact.tenant_id}/runs/{artifact.run_id}/artifacts/"
        if not key.startswith(expected):
            raise ValueError("artifact URI is outside its tenant/run scope")
        self._validate_key(key)
        return key

    @staticmethod
    def _validate_key(key: str) -> None:
        if (
            not key.startswith("tenants/")
            or "/runs/" not in key
            or "/artifacts/" not in key
            or ".." in key.split("/")
        ):
            raise ValueError("artifact storage key is invalid")
