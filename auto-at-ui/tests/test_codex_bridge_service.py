"""No provider, browser or database access; service launch count is authoritative."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import pytest
import test_codex_bridge_spool as spool_tests
from application.codex_bridge import BridgeService
from auto_at.contracts.codex_bridge import CodexBridgeReadiness, CodexStop
from config import Settings
from domain.codex_bridge import BridgeProcessResult

published = spool_tests.published


class FakeProcess:
    def __init__(self):
        self.calls = 0

    async def run(self, *_args):
        self.calls += 1
        return BridgeProcessResult(output=CodexStop(reason="complete"))


def test_file_readiness_rejects_wrong_tenant_expired_heartbeat_and_unavailable_model(published):
    from infrastructure.codex_bridge.doctor import FileReadiness

    spool, req = published
    bridge = service(spool, req)
    bridge.settings.codex_bridge_container_spool = str(spool.root)
    reader = FileReadiness(bridge.settings)
    assert not reader.read(req.tenant_id, datetime.now(UTC)).ready
    spool.heartbeat(bridge.readiness.model_dump(mode="json"))
    assert reader.read(req.tenant_id, datetime.now(UTC)).ready
    assert not reader.read("foreign", datetime.now(UTC)).ready
    assert not reader.read(req.tenant_id, datetime.now(UTC) + timedelta(seconds=11)).ready
    unavailable = bridge.readiness.model_copy(update={"model_access": "unavailable"})
    spool.heartbeat(unavailable.model_dump(mode="json"))
    assert not reader.read(req.tenant_id, datetime.now(UTC)).ready


def service(spool, req, process=None, *, ready=True):
    settings = Settings(
        _env_file=None, codex_bridge_enabled=True, codex_bridge_id=req.bridge_id,
        codex_bridge_allowed_tenant=req.tenant_id, codex_bridge_host_spool=str(spool.root),
        codex_bridge_executable="/usr/local/bin/codex",
    )
    return BridgeService(
        settings, spool, process or FakeProcess(), lambda *_args: b"synthetic",
        CodexBridgeReadiness(configured=True, online=True, authenticated=True,
                             capabilities_qualified=ready),
    )


@pytest.mark.parametrize("offset,ready", [(0.5, True), (2, False), (-10, False)])
def test_readiness_uses_end_of_read_without_relaxing_future_or_stale_limits(
    published, monkeypatch, offset, ready,
):
    from infrastructure.codex_bridge.doctor import FileReadiness

    spool, req = published
    bridge = service(spool, req)
    bridge.settings.codex_bridge_container_spool = str(spool.root)
    spool.heartbeat(bridge.readiness.model_dump(mode="json"))
    now = datetime.now(UTC)
    data = json.loads((spool.root / ".heartbeat.json").read_text())
    data["recorded_at"] = (now + timedelta(seconds=offset)).isoformat()
    spool._write(spool.root, ".heartbeat.json", json.dumps(data).encode())
    ticks = iter([100.0, 101.0])
    monkeypatch.setattr("infrastructure.codex_bridge.doctor.monotonic", lambda: next(ticks, 101.0))
    assert FileReadiness(bridge.settings).read(req.tenant_id, now).ready is ready


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_relaunch(published):
    spool, req = published
    bridge = service(spool, req)
    assert await bridge.run_once() == 1
    assert await bridge.run_once() == 0
    assert bridge.process.calls == 1
    assert spool.result(req).output.reason == "complete"


@pytest.mark.parametrize("stage", ["plain", "open"])
@pytest.mark.parametrize("variant", [
    "transient", "persistent", "permission", "stale", "future", "foreign", "malformed", "offline",
])
def test_readiness_retries_only_missing_heartbeat_and_revalidates_every_field(
    published, monkeypatch, stage, variant,
):
    from pathlib import Path

    from infrastructure.codex_bridge import doctor
    from infrastructure.codex_bridge import spool as spool_module

    spool, req = published
    bridge = service(spool, req)
    bridge.settings.codex_bridge_container_spool = str(spool.root)
    spool.heartbeat(bridge.readiness.model_dump(mode="json"))
    heartbeat = spool.root / ".heartbeat.json"
    data = json.loads(heartbeat.read_text())
    now = datetime.now(UTC)
    if variant in {"stale", "future"}:
        data["recorded_at"] = (now + timedelta(
            seconds=-60 if variant == "stale" else 60,
        )).isoformat()
    elif variant == "foreign":
        data["tenant_id"] = "foreign"
    elif variant == "offline":
        data["readiness"]["online"] = False
    heartbeat.write_text("{" if variant == "malformed" else json.dumps(data))
    attempts, sleeps = [], []
    monkeypatch.setattr(doctor, "sleep", sleeps.append, raising=False)

    def inject(path):
        if path == heartbeat:
            attempts.append(path)
            if variant == "permission":
                raise PermissionError(13, "fixture")
            if len(attempts) == 1 or variant == "persistent":
                raise FileNotFoundError(2, "fixture")

    if stage == "plain":
        original = spool_module._plain

        def plain(path, **kwargs):
            inject(path)
            return original(path, **kwargs)

        monkeypatch.setattr(spool_module, "_plain", plain)
    else:
        original = Path.open

        def opened(path, *args, **kwargs):
            inject(path)
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", opened)
    result = doctor.FileReadiness(bridge.settings).read(req.tenant_id, now)
    assert result.ready is (variant == "transient")
    assert len(attempts) == (3 if variant == "persistent" else 1 if variant == "permission" else 2)
    assert sleeps == ([.01, .01] if variant == "persistent" else
                      [] if variant == "permission" else [.01])


@pytest.mark.asyncio
async def test_verified_response_schema_is_sent_in_prompt(published):
    spool, req = published
    _, schema = spool.verify_inputs(req)

    class Capture(FakeProcess):
        async def run(self, request, directory, prompt, stop):
            payload = json.loads(prompt[prompt.index(b'{"response_schema":'):])
            assert payload["response_schema"] == json.loads(schema)
            assert b"without Markdown fences" in prompt
            return await super().run(request, directory, prompt, stop)

    bridge = service(spool, req, Capture())
    assert await bridge.run_once() == 1
    assert bridge.process.calls == 1


@pytest.mark.asyncio
async def test_interrupted_claim_is_terminal_without_relaunch(published):
    spool, req = published
    spool.claim(req)
    bridge = service(spool, req)
    assert await bridge.run_once() == 1
    assert bridge.process.calls == 0
    assert spool.result(req).failure_code == "bridge_interrupted"
    assert not spool.has_file(req, "dom.json")


@pytest.mark.asyncio
async def test_cancelled_job_and_unqualified_bridge_cannot_launch(published):
    spool, req = published
    bridge = service(spool, req, ready=False)
    assert await bridge.run_once() == 0
    spool.cancel(req)
    bridge = service(spool, req)
    assert await bridge.run_once() == 1
    assert bridge.process.calls == 0
    assert spool.result(req).failure_code == "bridge_cancelled"


@pytest.mark.asyncio
async def test_revocation_during_execution_discards_late_output(published):
    spool, req = published
    class Revoke(FakeProcess):
        async def run(self, *_args):
            spool.cancel(req)
            return await super().run()
    bridge = service(spool, req, Revoke())
    assert await bridge.run_once() == 1
    assert spool.result(req).failure_code == "bridge_cancelled"


@pytest.mark.asyncio
async def test_missing_authorization_waits_then_can_start(published):
    spool, req = published
    (spool.path(req.job_id) / "authorization.json").unlink()
    bridge = service(spool, req)
    assert await bridge.run_once() == 0
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=5))
    assert await bridge.run_once() == 1


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="Linux Compose producer flock contention")
async def test_publication_lock_contention_defers_scan_without_losing_readiness(published):
    spool, req = published
    bridge = service(spool, req)
    with spool.lock():
        assert await bridge.run_once() == 0
    assert bridge.readiness.ready
    assert bridge.process.calls == 0
    assert await bridge.run_once() == 1
    assert bridge.process.calls == 1


@pytest.mark.asyncio
async def test_permission_failure_is_not_treated_as_lock_contention(published, monkeypatch):
    spool, req = published
    bridge = service(spool, req)

    def denied(_now):
        raise PermissionError("synthetic permission failure")

    monkeypatch.setattr(spool, "reconcile", denied)
    with pytest.raises(PermissionError):
        await bridge.run_once()
    assert bridge.process.calls == 0


@pytest.mark.asyncio
async def test_idle_service_owns_lock_and_stops_heartbeat(published):
    spool, req = published
    bridge = service(spool, req)
    stopped = asyncio.Event()
    running = asyncio.create_task(bridge.serve(stopped))
    try:
        for _ in range(100):
            if (spool.root / ".heartbeat.json").exists():
                break
            await asyncio.sleep(0.01)
        assert (spool.root / ".heartbeat.json").exists()
        with pytest.raises(OSError):
            await service(spool, req).serve(asyncio.Event())
    finally:
        stopped.set()
        await asyncio.wait_for(running, timeout=3)
    import json
    heartbeat = json.loads((spool.root / ".heartbeat.json").read_bytes())
    assert heartbeat["readiness"]["online"] is False
