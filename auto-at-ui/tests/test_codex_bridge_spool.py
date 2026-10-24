"""Filesystem behavior with synthetic data; no CLI or app database is used."""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from auto_at.contracts.codex_bridge import canonical_bytes
from infrastructure.codex_bridge.spool import FileSpool, SpoolError
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
