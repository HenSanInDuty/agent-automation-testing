"""Filesystem behavior with synthetic data; no CLI or app database is used."""

import errno
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from auto_at.contracts.codex_bridge import canonical_bytes
from infrastructure.codex_bridge.spool import RECEIPT_CLOCK_SKEW, FileSpool, SpoolError
from infrastructure.observability.logging import JsonFormatter
from test_codex_bridge_contracts import observation, request, response


def job():
    now = datetime.now(UTC)
    obs = observation(captured_at=now)
    schema = b'{"type":"object"}'
    req = request(obs, created_at=now, deadline=now + timedelta(seconds=120))
    req = req.model_copy(update={"inputs": req.inputs.model_copy(update={
        "schema_sha256": hashlib.sha256(schema).hexdigest(), "schema_bytes": len(schema),
    })})
    return req, canonical_bytes(obs), schema


@pytest.fixture
def published(tmp_path):
    req, dom, schema = job()
    spool = FileSpool(tmp_path / "jobs", req.bridge_id, req.tenant_id)
    spool.publish(req, dom, schema)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=10))
    return spool, req


def test_atomic_publication_integrity_and_exclusive_claim(published):
    spool, req = published
    assert spool.jobs() == [req.job_id]
    assert spool.load(req.job_id) == req
    spool.verify_inputs(req)
    spool.claim(req)
    with pytest.raises(FileExistsError):
        spool.claim(req)
    assert not spool.has_file(req, "screenshot.png")


@pytest.mark.parametrize("name", [".atomic-fixture", "raw-output.json"])
def test_request_scan_survives_consumed_temporary_file(published, monkeypatch, name):
    import infrastructure.codex_bridge.spool as module

    spool, req = published
    transient = spool.path(req.job_id) / name
    transient.write_bytes(b"private synthetic output")
    original = module._plain

    def racing(path, **kwargs):
        if path == transient and path.exists():
            path.unlink()
        return original(path, **kwargs)

    monkeypatch.setattr(module, "_plain", racing)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=8))
    assert spool.load(req.job_id) == req


def test_missing_progress_waits_but_malformed_receipt_fails(published, monkeypatch):
    spool, req = published
    spool.claim(req)
    spool.record_stage(req, "claimed")
    original = spool.read_file
    pending = True

    def read(directory, name, limit):
        nonlocal pending
        if name == "events.jsonl" and pending:
            pending = False
            raise FileNotFoundError("synthetic shared filesystem race")
        return original(directory, name, limit)

    monkeypatch.setattr(spool, "read_file", read)
    assert spool.stages(req) == ()
    assert spool.stages(req)[0].stage == "claimed"
    (spool.path(req.job_id) / "events.jsonl").write_bytes(b"malformed\n")
    with pytest.raises(ValueError):
        spool.stages(req)


def test_file_io_diagnostic_identifies_operation_without_leaking_payloads(
    published, monkeypatch, caplog,
):
    import infrastructure.codex_bridge.spool as module

    spool, req = published
    failure = OSError(errno.EIO, "private-secret-message", "/private/path/events.jsonl")

    def failed_fstat(_fd):
        raise failure

    monkeypatch.setattr(module.os, "fstat", failed_fstat)
    with pytest.raises(OSError) as caught:
        spool.read_file(spool.path(req.job_id), "request.json", 16_384)
    assert caught.value is failure
    record = next(r for r in caplog.records if getattr(r, "event", None)
                  == "codex.spool.read_failed")
    encoded = JsonFormatter("synthetic", "test").format(record)
    payload = json.loads(encoded)
    assert payload["job_id"] == str(req.job_id)
    assert payload["io_operation"] == "fstat" and payload["file_name"] == "request.json"
    assert payload["errno"] == errno.EIO and payload["errno_name"] == "EIO"
    assert payload["code_locations"][-1]["function"] == "read_file"
    assert "private-secret" not in encoded and "/private/path" not in encoded
    assert "task_intent" not in encoded


def test_cancel_and_stale_authorization_prevent_launch(published):
    spool, req = published
    later = datetime.now(UTC) + timedelta(seconds=11)
    assert spool.stop_reason(req, later) == "bridge_policy_revoked"
    spool.cancel(req)
    assert spool.stop_reason(req, datetime.now(UTC)) == "bridge_cancelled"
    with pytest.raises(SpoolError):
        spool.claim(req)


def test_duplicate_queue_bound_and_wrong_scope_are_rejected(published):
    spool, req = published
    spool.max_pending = 1
    with pytest.raises(SpoolError, match="queue_full"):
        spool.publish(req, b"", b"")
    with pytest.raises(SpoolError, match="scope"):
        spool.cancel(req.model_copy(update={"tenant_id": "other"}))


@pytest.mark.parametrize("name", ["dom.json", "response.schema.json"])
def test_changed_payload_never_claims(published, name):
    spool, req = published
    (spool.path(req.job_id) / name).write_bytes(b"changed")
    with pytest.raises(ValueError):
        spool.claim(req)
    assert not spool.has_file(req, "claim.json")


def test_failed_publish_leaves_no_visible_job(tmp_path):
    req, dom, schema = job()
    spool = FileSpool(tmp_path / "jobs", req.bridge_id, req.tenant_id)
    with pytest.raises(SpoolError):
        spool.publish(req, dom, schema + b"bad")
    assert spool.jobs() == []
    assert not list(spool.root.glob(".staging-*"))


def test_consumer_lock_excludes_duplicate_worker(published):
    spool, _req = published
    with spool.lock(consumer=True), pytest.raises(OSError), spool.lock(consumer=True):
        pass


def test_result_identity_and_acknowledgement(published):
    spool, req = published
    now = datetime.now(UTC)
    result = response(req, started_at=req.created_at, completed_at=now)
    spool.complete(req, result)
    assert spool.result(req) == result
    spool.acknowledge(req)
    with spool.lock(consumer=True):
        spool.reconcile(datetime.now(UTC))
    assert spool.jobs() == []


def test_expiry_and_crashed_staging_cleanup(published):
    spool, req = published
    staging = spool.root / f".staging-{uuid4()}"
    staging.mkdir()
    (staging / "dom.json").write_bytes(b"synthetic")
    with spool.lock(consumer=True):
        spool.reconcile(req.deadline)
    assert not staging.exists()
    assert spool.jobs() == []


def test_long_authorization_lease_rejected(published):
    spool, req = published
    with pytest.raises(SpoolError, match="expiry"):
        spool.authorize(req, datetime.now(UTC) + timedelta(seconds=20))


def test_failed_atomic_response_never_exposes_partial_bytes(published, monkeypatch):
    import os
    spool, req = published
    result = response(req, started_at=req.created_at, completed_at=datetime.now(UTC))
    def disk_full(*_args):
        raise OSError("synthetic disk full")
    monkeypatch.setattr(os, "replace", disk_full)
    with pytest.raises(OSError):
        spool.complete(req, result)
    assert not spool.has_file(req, "response.json")
    assert not list(spool.path(req.job_id).glob(".atomic-*"))


def test_unknown_file_blocks_cleanup(published):
    spool, req = published
    (spool.path(req.job_id) / "unknown.txt").write_text("keep")
    with pytest.raises(SpoolError):
        spool.load(req.job_id)
    with pytest.raises(SpoolError):
        spool._remove(spool.path(req.job_id))
    assert (spool.path(req.job_id) / "unknown.txt").read_text() == "keep"


def test_deadline_and_unconsented_image_rejected(published):
    spool, req = published
    assert spool.stop_reason(req, req.deadline) == "bridge_deadline_exceeded"
    (spool.path(req.job_id) / "screenshot.png").write_bytes(b"synthetic")
    with pytest.raises(SpoolError, match="unconsented"):
        spool.claim(req)


def test_request_identity_cannot_be_replaced(published):
    spool, req = published
    changed = req.model_copy(update={"job_id": uuid4()})
    (spool.path(req.job_id) / "request.json").write_bytes(canonical_bytes(changed))
    with pytest.raises(SpoolError, match="identity"):
        spool.load(req.job_id)


def test_progress_is_closed_coalesced_and_bounded(published):
    spool, req = published
    for _ in range(100):
        spool.record_stage(req, "running")
    data = spool.read_file(spool.path(req.job_id), "events.jsonl", 65_536)
    assert len(data.splitlines()) == 1
    with pytest.raises(ValueError):
        spool.record_stage(req, "raw model text")
    for index in range(100):
        spool.record_stage(req, "claimed" if index % 2 else "running")
    assert len(spool.read_file(spool.path(req.job_id), "events.jsonl", 65_536).splitlines()) == 64


@pytest.mark.skipif(os.name == "nt", reason="symlink adversary checked in Linux image")
def test_symlink_job_and_input_never_read_or_delete_outside(tmp_path):
    req, dom, schema = job()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("keep")
    spool = FileSpool(tmp_path / "jobs", req.bridge_id, req.tenant_id)
    (spool.root / str(req.job_id)).symlink_to(outside, target_is_directory=True)
    with pytest.raises(SpoolError):
        spool.load(req.job_id)
    (spool.root / str(req.job_id)).unlink()
    spool.publish(req, dom, schema)
    (spool.path(req.job_id) / "dom.json").unlink()
    (spool.path(req.job_id) / "dom.json").symlink_to(sentinel)
    with pytest.raises(SpoolError):
        spool.verify_inputs(req)
    with pytest.raises(SpoolError):
        spool._remove(spool.path(req.job_id))
    assert sentinel.read_text() == "keep"


def _aged_job(tmp_path):
    """Request created 30 s ago so a lagging `now` is not rejected as pre-creation."""
    now = datetime.now(UTC)
    obs = observation(captured_at=now - timedelta(seconds=30))
    schema = b'{"type":"object"}'
    req = request(obs, created_at=now - timedelta(seconds=30),
                  deadline=now + timedelta(seconds=120))
    req = req.model_copy(update={"inputs": req.inputs.model_copy(update={
        "schema_sha256": hashlib.sha256(schema).hexdigest(), "schema_bytes": len(schema),
    })})
    spool = FileSpool(tmp_path / "jobs", req.bridge_id, req.tenant_id)
    spool.publish(req, canonical_bytes(obs), schema)
    return spool, req


def test_reauthorization_between_poll_clock_and_read_is_not_revoked(tmp_path):
    # r9: the bridge samples `now`, then the control plane rewrites the receipt
    # (recorded_at > now) before the bridge reads it. That is a healthy handoff.
    spool, req = _aged_job(tmp_path)
    sampled = datetime.now(UTC)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    assert spool.stop_reason(req, sampled) is None


def test_receipt_recorded_far_in_the_future_is_revoked(tmp_path):
    spool, req = _aged_job(tmp_path)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    lagging = datetime.now(UTC) - RECEIPT_CLOCK_SKEW - timedelta(seconds=1)
    assert spool.stop_reason(req, lagging) == "bridge_policy_revoked"


def test_expired_missing_and_overdue_authorization_still_stop(tmp_path):
    spool, req = _aged_job(tmp_path)
    assert spool.stop_reason(req, datetime.now(UTC)) == "bridge_policy_revoked"  # missing
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    expired = datetime.now(UTC) + timedelta(seconds=3)
    assert spool.stop_reason(req, expired) == "bridge_policy_revoked"
    assert spool.stop_reason(req, req.deadline) == "bridge_deadline_exceeded"


def test_receipt_with_excessive_ttl_is_revoked(tmp_path, monkeypatch):
    spool, req = _aged_job(tmp_path)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=2))
    original = spool._receipt

    def long_ttl(request, status, expiry, nonce):
        return original(request, status, req.deadline, nonce)

    monkeypatch.setattr(spool, "_receipt", long_ttl)
    spool._write(spool.path(req.job_id), "authorization.json",
                 canonical_bytes(long_ttl(req, "queued", None, UUID(int=0))))
    monkeypatch.undo()
    assert spool.stop_reason(req, datetime.now(UTC)) == "bridge_policy_revoked"


def _flaky_fstat(module, monkeypatch, failures):
    """`os.fstat` raises the queued errors first, then behaves normally."""
    real, pending = module.os.fstat, list(failures)

    def fstat(fd):
        if pending:
            raise pending.pop(0)
        return real(fd)

    monkeypatch.setattr(module.os, "fstat", fstat)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    return pending


@pytest.mark.parametrize("code", ["ENODATA", "ESTALE"])
def test_a_file_replaced_under_the_reader_is_read_again(published, monkeypatch, caplog, code):
    # ADR-046 (sprint Q4): the writer's atomic replace surfaced as ENODATA on the bind mount.
    import infrastructure.codex_bridge.spool as module

    spool, req = published
    expected = spool.read_file(spool.path(req.job_id), "request.json", 16_384)
    pending = _flaky_fstat(module, monkeypatch, [OSError(getattr(errno, code), "replaced")])
    assert spool.read_file(spool.path(req.job_id), "request.json", 16_384) == expected
    assert pending == []
    logged = [r for r in caplog.records if getattr(r, "event", None) == "codex.spool.read_failed"]
    assert len(logged) == 1 and logged[0].read_attempt == 1  # the lost attempt stays visible


def test_the_reread_is_bounded_and_then_raises_the_original_error(published, monkeypatch):
    import infrastructure.codex_bridge.spool as module

    spool, req = published
    failures = [OSError(errno.ENODATA, "replaced") for _ in range(5)]
    pending = _flaky_fstat(module, monkeypatch, failures)
    with pytest.raises(OSError) as caught:
        spool.read_file(spool.path(req.job_id), "request.json", 16_384)
    assert caught.value.errno == errno.ENODATA
    assert len(pending) == 5 - (1 + len(module.READ_RETRY_DELAYS))


def test_other_io_errors_are_never_read_again(published, monkeypatch):
    import infrastructure.codex_bridge.spool as module

    spool, req = published
    failures = [OSError(errno.EIO, "disk"), OSError(errno.EIO, "disk")]
    pending = _flaky_fstat(module, monkeypatch, failures)
    with pytest.raises(OSError):
        spool.read_file(spool.path(req.job_id), "request.json", 16_384)
    assert len(pending) == 1


def test_a_link_count_seen_during_a_rename_is_read_again(published, monkeypatch):
    # ADR-046: a live run ended `bridge_offline` when the heartbeat showed two links mid-rename.
    import infrastructure.codex_bridge.spool as module

    spool, req = published
    expected = spool.read_file(spool.path(req.job_id), "request.json", 16_384)
    real, calls = module.os.fstat, []

    def fstat(fd):
        info = real(fd)
        calls.append(fd)
        if len(calls) == 1:
            return os.stat_result((info.st_mode, info.st_ino, info.st_dev, 2, *info[4:10]))
        return info

    monkeypatch.setattr(module.os, "fstat", fstat)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    assert spool.read_file(spool.path(req.job_id), "request.json", 16_384) == expected
    assert len(calls) == 2


def test_a_file_that_stays_hard_linked_is_still_refused(published, monkeypatch):
    import infrastructure.codex_bridge.spool as module

    spool, req = published
    real, calls = module.os.fstat, []

    def fstat(fd):
        info = real(fd)
        calls.append(fd)
        return os.stat_result((info.st_mode, info.st_ino, info.st_dev, 2, *info[4:10]))

    monkeypatch.setattr(module.os, "fstat", fstat)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    with pytest.raises(module.SpoolError):
        spool.read_file(spool.path(req.job_id), "request.json", 16_384)
    assert len(calls) == 1 + len(module.READ_RETRY_DELAYS)
