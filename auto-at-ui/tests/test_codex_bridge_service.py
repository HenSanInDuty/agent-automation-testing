"""No provider, browser or database access; service launch count is authoritative."""

import asyncio
import json
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


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_relaunch(published):
    spool, req = published
    bridge = service(spool, req)
    assert await bridge.run_once() == 1
    assert await bridge.run_once() == 0
    assert bridge.process.calls == 1
    assert spool.result(req).output.reason == "complete"


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
