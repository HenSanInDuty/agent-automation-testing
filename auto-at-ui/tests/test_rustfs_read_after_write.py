"""RustFS read-after-write lag must not turn a durable frame into an unknown outcome.

Round 21 attempt 3 (session 0d840885-2a5d-4b86-b1b0-5c31db61f09e, operation 27):
the PUT succeeded, but the immediate verification GET hit RustFS `FileCorrupt`
("file size ... = 0") and an aborted body, so the operation was persisted as
unknown / worker_response_lost. Round-20 operation 85 shows the same signature.
"""

import os
from hashlib import sha256
from uuid import uuid4

import pytest
from botocore.exceptions import ResponseStreamingError
from config import Settings
from domain.vision import VisualSessionScope
from infrastructure.artifacts import rustfs
from infrastructure.artifacts.rustfs import ArtifactStorageError, RustFSArtifactStore
from test_rustfs_operation_storage import disposable_rustfs  # noqa: F401
from vision_trace_fixtures import frame, operation


class Body:
    def __init__(self, data, fail=False):
        self.data, self.fail = data, fail

    def read(self, _limit):
        if self.fail:
            raise ResponseStreamingError(error="body write aborted")
        return self.data

    def close(self):
        pass


class LaggingClient:
    """Serves the first `lag` reads like RustFS does right after a PUT."""

    def __init__(self, content, record, *, lag, mode="aborted"):
        self.content, self.record, self.lag, self.mode = content, record, lag, mode
        self.reads = 0

    def head_bucket(self, **_):
        return {}

    def put_object(self, **_):
        return {}

    def get_object(self, **_):
        self.reads += 1
        meta = self.record.metadata
        headers = {"ContentType": meta.content_type, "Metadata": {"sha256": meta.checksum}}
        if self.reads <= self.lag:
            if self.mode == "aborted":
                return {**headers, "ContentLength": meta.byte_count,
                        "Body": Body(b"", fail=True)}
            return {**headers, "ContentLength": 0, "Body": Body(b"")}
        return {**headers, "ContentLength": meta.byte_count, "Body": Body(self.content)}


def store_with(client, monkeypatch):
    monkeypatch.setattr(rustfs, "sleep", lambda _seconds: None)
    store = RustFSArtifactStore(Settings(_env_file=None, rustfs_bucket="fixture"), client)
    store._bucket_ready = True
    return store


def fixture_frame(content=b"\x89PNG\r\n\x1a\nafter-frame"):
    intent = operation(VisualSessionScope("fixture-tenant", uuid4(), uuid4()))
    return frame(intent, "after", content), content


@pytest.mark.parametrize("mode", ["aborted", "empty"])
def test_write_survives_transient_read_after_write_lag(monkeypatch, mode):
    record, content = fixture_frame()
    client = LaggingClient(content, record, lag=2, mode=mode)
    store_with(client, monkeypatch).write_operation_frame(record, content)
    assert client.reads == 3


def test_persistent_failure_still_fails_after_bounded_attempts(monkeypatch):
    record, content = fixture_frame()
    client = LaggingClient(content, record, lag=100)
    with pytest.raises(ArtifactStorageError):
        store_with(client, monkeypatch).write_operation_frame(record, content)
    assert client.reads == len(rustfs.OPERATION_FRAME_READ_RETRY_DELAYS) + 1


def test_different_bytes_are_never_accepted(monkeypatch):
    record, content = fixture_frame()
    other = b"\x89PNG\r\n\x1a\nother-writer"
    client = LaggingClient(other, record, lag=0)
    client.record = frame(operation(VisualSessionScope("t", uuid4(), uuid4())), "after", other)
    with pytest.raises(ValueError):
        store_with(client, monkeypatch).read_operation_frame(record)
    assert sha256(other).hexdigest() != record.metadata.checksum


def test_retry_budget_is_short():
    assert sum(rustfs.OPERATION_FRAME_READ_RETRY_DELAYS) < 2


@pytest.mark.skipif(os.environ.get("RUSTFS_STRESS") != "1",
                    reason="set RUSTFS_STRESS=1 to stress the pinned RustFS image")
def test_pinned_rustfs_large_frames_verify_immediately(disposable_rustfs):  # noqa: F811
    store = disposable_rustfs
    scope = VisualSessionScope("fixture-tenant", uuid4(), uuid4())
    for index in range(int(os.environ.get("RUSTFS_STRESS_FRAMES", "40"))):
        content = b"\x89PNG\r\n\x1a\n" + os.urandom(1_000_000 + index)
        record = frame(operation(scope), "after", content)
        store.write_operation_frame(record, content)
