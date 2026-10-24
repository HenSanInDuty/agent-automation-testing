import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from agents.vision.codex_service import task_context
from application.codex_candidates import CodexUnavailable
from application.vision_model_batch import VisionModelSession
from auto_at.contracts.codex_bridge import CodexBridgeReadiness, canonical_bytes
from infrastructure.codex_bridge.spool import FileSpool
from infrastructure.vision.codex_batch import CodexModelBatch
from test_codex_bridge_contracts import response
from test_codex_candidate_service import bound_observation, codex_policy


class Readiness:
    def __init__(self):
        self.online = True

    def read(self, *_args):
        return CodexBridgeReadiness(
            configured=True, online=self.online, authenticated=True, capabilities_qualified=True,
        )


class Gateway:
    def __init__(self):
        self.events = []

    async def register(self, req):
        self.events.append(("registered", req))

    async def poll(self, req, stages):
        pass

    async def cleanup_pending(self, req):
        pass

    async def finish(self, req, response):
        self.events.append(("finished", response))

    async def cancel(self, req, reason):
        self.events.append(("cancelled", reason))


@pytest.fixture
def harness(tmp_path):
    bound = bound_observation()
    obs = bound.observation
    bridge_id = uuid4()
    spool = FileSpool(tmp_path / "jobs", bridge_id, obs.tenant_id)
    gateway, readiness, policy = Gateway(), Readiness(), codex_policy()
    batch = CodexModelBatch(bridge_id=bridge_id, spool=spool, gateway=gateway,
                           readiness=readiness, poll_seconds=0.01)
    args = dict(
        session=VisionModelSession(obs.tenant_id, obs.session_id, "codex_cli", "gpt-6-luna",
                                   obs.project_id, uuid4(), obs.fencing_token),
        bound=bound, context=task_context("Exercise fixture"), policy=policy, sequence=1,
        deadline=datetime.now(UTC) + timedelta(seconds=20), max_candidates=2, image=None,
        check_policy=lambda: policy,
    )
    return batch, args, spool, gateway, readiness


async def wait_authorized(spool):
    for _ in range(100):
        jobs = spool.jobs()
        if jobs:
            req = spool.load(jobs[0])
            if spool.stop_reason(req, datetime.now(UTC)) is None:
                return req
        await asyncio.sleep(0.01)
    raise AssertionError("synthetic job not authorized")


@pytest.mark.asyncio
async def test_durable_registration_precedes_publication_and_result_is_acknowledged(harness):
    batch, args, spool, gateway, _ready = harness
    task = asyncio.create_task(batch(**args))
    req = await wait_authorized(spool)
    assert gateway.events[0] == ("registered", req)
    assert req.context == args["context"] and req.prompt_version == "codex-dom-v6"
    assert not spool.has_file(req, "screenshot.png")
    result = response(req, started_at=datetime.now(UTC), completed_at=datetime.now(UTC))
    spool.complete(req, result)
    assert await task == result
    assert gateway.events[-1][0] == "finished"
    assert spool.has_file(req, "ack.json")


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["hash", "scope", "model", "late"])
async def test_wrong_or_late_result_never_returns_a_candidate(harness, condition):
    batch, args, spool, gateway, _ready = harness
    if condition == "late":
        args["deadline"] = datetime.now(UTC) + timedelta(seconds=1)
    task = asyncio.create_task(batch(**args))
    req = await wait_authorized(spool)
    result = response(req, started_at=datetime.now(UTC), completed_at=datetime.now(UTC))
    changes = {"hash": {"request_hash": "f" * 64}, "scope": {"session_id": uuid4()},
               "model": {"actual_model": "other"}, "late": {}}[condition]
    if condition == "late":
        await asyncio.sleep(max(0, (args["deadline"] - datetime.now(UTC)).total_seconds()) + 0.05)
    else:
        bad = result.model_copy(update=changes)
        (spool.path(req.job_id) / "response.json").write_bytes(canonical_bytes(bad))
    with pytest.raises((CodexUnavailable, TimeoutError)):
        await task
    assert gateway.events[-1][0] == "cancelled"
    assert spool.has_file(req, "cancel.json")
    assert not spool.has_file(req, "ack.json")


@pytest.mark.asyncio
async def test_revocation_while_queued_cancels_job_and_stops_authorization(harness):
    batch, args, spool, gateway, _ready = harness
    task = asyncio.create_task(batch(**args))
    req = await wait_authorized(spool)
    args["policy"].enabled = False
    with pytest.raises(CodexUnavailable, match="policy_changed"):
        await task
    assert gateway.events[-1][0] == "cancelled"
    assert spool.stop_reason(req, datetime.now(UTC)) == "bridge_cancelled"


@pytest.mark.asyncio
async def test_offline_bridge_and_wrong_tenant_fail_before_registration(harness):
    batch, args, spool, gateway, ready = harness
    ready.online = False
    with pytest.raises(CodexUnavailable, match="bridge_offline"):
        await batch(**args)
    assert not gateway.events and not spool.jobs()
    ready.online = True
    args["session"] = VisionModelSession("other", uuid4(), "codex_cli", "gpt-6-luna")
    with pytest.raises(CodexUnavailable, match="bridge_stale_result"):
        await batch(**args)
    assert not gateway.events and not spool.jobs()


@pytest.mark.asyncio
async def test_task_cancellation_cancels_owned_file_job(harness):
    batch, args, spool, gateway, _ready = harness
    task = asyncio.create_task(batch(**args))
    req = await wait_authorized(spool)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gateway.events[-1][0] == "cancelled"
    assert spool.has_file(req, "cancel.json")
