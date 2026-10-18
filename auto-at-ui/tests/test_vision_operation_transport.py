"""Synthetic HTTP and conditional S3 responses; no provider or application database."""

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import httpx
import pytest
from auto_at.contracts.vision_worker import VisualWorkerIdentity, VisualWorkerOperationResult
from botocore.exceptions import ClientError
from config import Settings
from domain.vision import VisualSessionScope
from infrastructure.artifacts.rustfs import RustFSArtifactStore
from infrastructure.vision_worker import HttpVisualWorker, VisualWorkerUnavailable
from vision_trace_fixtures import evolve, frame, operation

PNG = b"\x89PNG\r\n\x1a\nfixture"


def test_worker_transport_preserves_confirmed_click():
    intent, before, identity = fixture()
    now = datetime.now(UTC)
    operation = evolve(
        intent, action_kind="click", status="failed", ended_at=now,
        outcome_code="settle_timeout", actual_before_frame_id=before.metadata.id,
        after_unavailable_reason="capture_failed",
        executed_click=dict(x=0.4, y=0.5, viewport_width=1280, viewport_height=720,
                            before_frame_id=before.metadata.id, confirmed_at=now),
    )
    result = VisualWorkerOperationResult(
        operation=operation, frames=(before.metadata,), locator=None, prepared_handle=uuid4(),
        state_fingerprint=None, checkpoint=None, semantic_change="unavailable",
        duration_ms=1, acknowledged=False, replayable=False,
    )

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=result.model_dump(mode="json")),
        )) as client:
            return await HttpVisualWorker(client, "http://worker.test", "fixture-only").read(
                identity, intent.id,
            )

    assert asyncio.run(read()).operation.executed_click == operation.executed_click


@pytest.mark.parametrize("wrong_scope", [False, True])
def test_origin_observation_transport_checks_scope(wrong_scope):
    identity = VisualWorkerIdentity(
        tenant_id="tenant", project_id=uuid4(), session_id=uuid4(), fencing_token=3,
    )

    def response(request):
        assert request.url.path.endswith(f"/{identity.session_id}/origins")
        assert request.headers["x-auto-at-vision-fencing-token"] == "3"
        return httpx.Response(200, json={
            **identity.model_dump(mode="json"),
            "tenant_id": "other" if wrong_scope else "tenant", "items": [], "truncated": False,
        })

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            worker = HttpVisualWorker(client, "http://worker.test", "fixture-only")
            return await worker.origins(identity)

    if wrong_scope:
        with pytest.raises(VisualWorkerUnavailable):
            asyncio.run(read())
    else:
        assert asyncio.run(read()).items == ()


@pytest.mark.parametrize("failure", [None, "type", "signature", "oversize"])
def test_live_screen_transport_is_bounded_and_private(failure):
    identity = VisualWorkerIdentity(
        tenant_id="tenant", project_id=uuid4(), session_id=uuid4(), fencing_token=3,
    )

    def response(request):
        assert request.url.path.endswith(f"/{identity.session_id}/screen")
        assert request.headers["x-auto-at-vision-fencing-token"] == "3"
        assert request.headers["x-auto-at-vision-worker-secret"] == "fixture-only"
        return httpx.Response(200, content=(
            PNG + b"x" * 2_000_000 if failure == "oversize"
            else b"invalid" if failure == "signature" else PNG
        ), headers={"content-type": "text/plain" if failure == "type" else "image/png"})

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            return await HttpVisualWorker(client, "http://worker.test", "fixture-only").screen(
                identity,
            )

    if failure:
        with pytest.raises(VisualWorkerUnavailable):
            asyncio.run(read())
    else:
        assert asyncio.run(read()) == PNG


def fixture():
    scope = VisualSessionScope("tenant-fixture", uuid4(), uuid4())
    intent = operation(scope)
    record = frame(intent, "before", PNG)
    identity = VisualWorkerIdentity(
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        session_id=scope.session_id,
        fencing_token=1,
    )
    return intent, record, identity


@pytest.mark.parametrize("failure", [None, "oversize", "checksum", "type", "signature"])
def test_transport_checks_frame_bytes_and_sends_scoped_private_headers(failure):
    _, record, identity = fixture()
    metadata = record.metadata
    data = PNG + b"x" if failure == "oversize" else PNG
    data = b"x" * len(PNG) if failure in {"checksum", "signature"} else data
    if failure == "signature":
        from hashlib import sha256

        metadata = evolve(metadata, checksum=sha256(data).hexdigest())

    def response(request):
        assert request.headers["x-auto-at-vision-worker-secret"] == "fixture-only"
        assert request.headers["x-auto-at-vision-tenant-id"] == identity.tenant_id
        assert request.headers["x-auto-at-vision-project-id"] == str(identity.project_id)
        assert request.headers["x-auto-at-vision-fencing-token"] == "1"
        return httpx.Response(
            200,
            content=data,
            headers={"content-type": "text/plain" if failure == "type" else "image/png"},
        )

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            return await HttpVisualWorker(client, "http://worker.test", "fixture-only").frame(
                identity,
                metadata,
            )

    if failure:
        with pytest.raises(VisualWorkerUnavailable):
            asyncio.run(read())
    else:
        assert asyncio.run(read()) == PNG


@pytest.mark.parametrize("wrong_scope", [False, True])
def test_transport_rejects_cross_scope_or_wrong_operation_result(wrong_scope):
    intent, _, identity = fixture()
    remote = evolve(intent, tenant_id="other") if wrong_scope else evolve(intent, id=uuid4())
    result = VisualWorkerOperationResult(
        operation=remote,
        frames=(),
        locator=None,
        prepared_handle=uuid4(),
        state_fingerprint=None,
        checkpoint=None,
        semantic_change="unavailable",
        duration_ms=0,
        acknowledged=False,
        replayable=False,
    )

    async def read():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=result.model_dump(mode="json")),
            )
        ) as client:
            await HttpVisualWorker(client, "http://worker.test", "fixture-only").read(
                identity,
                intent.id,
            )

    with pytest.raises(VisualWorkerUnavailable, match="mismatch"):
        asyncio.run(read())


class ConditionalS3:
    def __init__(self):
        self.objects = {}
        self.last_body = None

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata, IfNoneMatch):
        assert IfNoneMatch == "*"
        if (Bucket, Key) in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Bucket, Key] = (Body, ContentType, Metadata)

    def get_object(self, *, Bucket, Key):
        content, content_type, metadata = self.objects[Bucket, Key]
        self.last_body = BytesIO(content)
        return {
            "Body": self.last_body,
            "ContentType": content_type,
            "ContentLength": len(content),
            "Metadata": metadata,
        }

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def test_conditional_storage_retry_cannot_overwrite_evidence_and_closes_body():
    intent, record, _ = fixture()
    client = ConditionalS3()
    store = RustFSArtifactStore(Settings(_env_file=None, rustfs_bucket="fixture"), client)
    store.write_operation_frame(record, PNG)
    store.write_operation_frame(record, PNG)
    assert store.read_operation_frame(record) == PNG
    assert client.last_body.closed
    different = frame(intent, "before", PNG + b"different")
    with pytest.raises(ValueError, match="verification"):
        store.write_operation_frame(different, PNG + b"different")
    assert client.last_body.closed
    assert store.read_operation_frame(record) == PNG
    store.delete_operation_frame(record)
    assert not client.objects


def test_corrupt_storage_bytes_or_metadata_fail_read_back():
    _, record, _ = fixture()
    client = ConditionalS3()
    store = RustFSArtifactStore(Settings(_env_file=None, rustfs_bucket="fixture"), client)
    store.write_operation_frame(record, PNG)
    content, content_type, metadata = client.objects["fixture", record.storage_key]
    client.objects["fixture", record.storage_key] = (b"x" * len(content), content_type, metadata)
    with pytest.raises(ValueError, match="checksum"):
        store.read_operation_frame(record)
    assert client.last_body.closed
