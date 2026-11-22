"""Round 20: an unproven after-frame outcome stays unknown and is classified by stage.

DB-free: the unit of work is faked, or the real one is given a factory that fails on use.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from application.vision_operations import (
    FAILURE_STAGES,
    ExecuteVisualOperation,
    VisualOperationStopped,
)
from auto_at.contracts.vision_worker import (
    VisualWorkerAction,
    VisualWorkerOperationResult,
    VisualWorkerPrepare,
)
from domain.vision import VisualSessionLease, VisualSessionScope
from infrastructure.persistence.vision_unit_of_work import (
    SqlAlchemyVisualTraceUnitOfWork,
    failure_stage,
)
from vision_trace_fixtures import MemoryFrameStore, evolve, frame, operation

PNG = b"\x89PNG\r\n\x1a\nfixture"
SECRET = "https://secret.example/?token=abc form-value-hunter2"


class FakeUow:
    """Persists only what the service commits; the after-frame commit raises `after_error`."""

    def __init__(self, after_error):
        self.after_error = after_error
        self.saved = {}
        self.commits = []

    def renew(self, lease):
        return lease

    def read_snapshot(self, scope):
        return {"operations": ()}

    def commit_prepared(self, lease, op):
        self.saved[op.id] = op
        return op

    def commit_operation(self, lease, op):
        self.saved[op.id] = op
        self.commits.append(op.status)
        return op

    def commit_captured(self, lease, record, content, op, locator=None, **kwargs):
        if record.metadata.role == "after":
            raise self.after_error
        self.saved[op.id] = op
        return op


class Worker:
    def __init__(self, intent, frame_error=None):
        self.intent, self.frame_error = intent, frame_error
        self.executions = 0
        self.result = None

    async def prepare(self, request):
        before = frame(self.intent, "before", PNG)
        self.result = VisualWorkerOperationResult(
            operation=evolve(self.intent, actual_before_frame_id=before.metadata.id),
            frames=(before.metadata,), locator=None, prepared_handle=uuid4(),
            state_fingerprint="a" * 64, checkpoint=None, semantic_change="unavailable",
            duration_ms=0, acknowledged=False, replayable=False,
        )
        return self.result

    async def execute(self, request):
        self.executions += 1
        after = frame(self.intent, "after", PNG)
        final = evolve(
            self.result.operation, status="completed", ended_at=datetime.now(UTC),
            outcome_code="observed", actual_after_frame_id=after.metadata.id,
        )
        self.result = evolve(
            self.result, operation=final,
            frames=(self.result.frames[0], after.metadata), semantic_change="changed",
        )
        return self.result

    async def read(self, identity, operation_id):
        return self.result

    async def frame(self, identity, metadata):
        if self.frame_error and metadata.role == "after":
            raise self.frame_error
        return PNG

    async def acknowledge(self, request):
        raise AssertionError("an unproven operation must not acknowledge staging")


def run(after_error, frame_error=None):
    scope = VisualSessionScope("tenant-a", uuid4(), uuid4())
    lease = VisualSessionLease(scope, uuid4(), 1, datetime.now(UTC) + timedelta(minutes=5))
    intent = operation(scope, expected_parent_fingerprint="a" * 64)
    uow, worker = FakeUow(after_error), Worker(intent, frame_error)
    service = ExecuteVisualOperation(
        uow, worker, lease, datetime.now(UTC) + timedelta(seconds=30), 10, 5000, lambda: None
    )
    request = VisualWorkerPrepare(
        **service.identity.model_dump(), operation_id=intent.id, purpose="setup",
        action=VisualWorkerAction(kind="navigate"), expected_state_fingerprint="a" * 64,
    )
    with pytest.raises(VisualOperationStopped) as stopped:
        asyncio.run(service.execute(intent, request))
    return service, uow, worker, intent, str(stopped.value)


def tagged(stage, error):
    with pytest.raises(type(error)):
        with failure_stage(stage):
            raise error
    return error


def test_after_commit_failure_stays_unknown_and_is_classified(caplog):
    error = tagged("db_checkpoint", ValueError(SECRET))
    with caplog.at_level(logging.WARNING):
        service, uow, worker, intent, reason = run(error)
    saved = uow.saved[intent.id]
    # Safety: outcome unproven -> unknown, never completed; the click is never repeated.
    assert saved.status == "unknown" and saved.outcome_code == "worker_response_lost"
    assert saved.actual_after_frame_id is None and worker.executions == 1
    assert reason == "operation_unavailable"
    assert service.last_failure == {
        "failure_stage": "db_checkpoint", "error_type": "ValueError", "error_module": "builtins",
        "operation_id": str(intent.id), "operation_sequence": 1,
        "outcome_code": "worker_response_lost",
    }
    record = next(r for r in caplog.records if r.event == "vision.operation.failure_stage")
    assert record.failure_stage == "db_checkpoint"
    assert "secret.example" not in repr(record.__dict__) and "hunter2" not in repr(record.__dict__)


def test_untagged_after_failure_falls_back_to_capture_after_phase():
    service, uow, _, intent, _ = run(RuntimeError(SECRET))
    assert uow.saved[intent.id].status == "unknown"
    assert service.last_failure["failure_stage"] == "capture_after"
    assert SECRET not in repr(service.last_failure)


def test_worker_frame_fetch_failure_is_classified_without_leaking_message():
    service, uow, _, intent, _ = run(RuntimeError("unused"), frame_error=OSError(SECRET))
    assert uow.saved[intent.id].status == "unknown"
    assert service.last_failure["failure_stage"] == "frame_fetch"
    assert service.last_failure["error_type"] == "OSError"
    assert SECRET not in repr(service.last_failure)


def test_innermost_stage_wins_and_unknown_names_are_not_reported():
    error = ValueError("x")
    with pytest.raises(ValueError):
        with failure_stage("db_commit"), failure_stage("db_frame"):
            raise error
    assert error.failure_stage == "db_frame"
    service, *_ = run(tagged("custom/<script>", RuntimeError("x")))
    assert service.last_failure["failure_stage"] == "unclassified"
    assert {"store_write", "store_readback", "db_commit", "capture_after"} <= FAILURE_STAGES


def _uow(store, factory=None):
    return SqlAlchemyVisualTraceUnitOfWork(factory or (lambda: pytest.fail("no DB")), store)


def _captured_inputs():
    scope = VisualSessionScope("tenant-a", uuid4(), uuid4())
    lease = VisualSessionLease(scope, uuid4(), 1, datetime.now(UTC) + timedelta(minutes=5))
    item = operation(scope)
    record = frame(item, "before", PNG)
    return lease, record, evolve(item, actual_before_frame_id=record.metadata.id)


def _capture(store, factory=None):
    lease, record, item = _captured_inputs()
    with pytest.raises(Exception) as caught:
        _uow(store, factory).commit_captured(lease, record, PNG, item)
    return caught.value


def test_real_uow_tags_store_write_readback_and_db_commit():
    class Down(MemoryFrameStore):
        def write_operation_frame(self, record, content):
            raise OSError("rustfs down")

    class Stale(MemoryFrameStore):
        def read_operation_frame(self, record):
            return b"stale"

    assert _capture(Down()).failure_stage == "store_write"
    assert _capture(Stale()).failure_stage == "store_readback"

    def broken_factory():
        raise RuntimeError("db down")

    error = _capture(MemoryFrameStore(), broken_factory)
    assert error.failure_stage == "db_commit"
