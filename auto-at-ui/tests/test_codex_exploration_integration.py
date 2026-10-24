"""Real browser, migrated owned DB and file transport with a pinned synthetic subprocess."""

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from agents.prompts.codex_exploration import build_prompt
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY
from application.codex_bridge import BridgeService
from application.codex_candidates import CodexCandidateService
from application.vision_trace_events import VisionTraceEventProcessor
from auto_at.contracts.codex_bridge import parse_codex_output
from config import Settings
from domain.codex_bridge import BridgeProcessResult
from domain.runs import OutboxEvent
from infrastructure.codex_bridge.process import EventReader
from infrastructure.codex_bridge.spool import FileSpool
from infrastructure.persistence.codex_bridge_repository import SqlAlchemyCodexJobGateway
from infrastructure.persistence.models import (
    ActivityEventModel,
    CodexBridgeJobModel,
    ProjectExecutionPolicyModel,
    VisualActionProposalModel,
)
from infrastructure.persistence.repositories import SqlAlchemyConfigurationRepository
from infrastructure.vision.codex_batch import CodexModelBatch
from infrastructure.vision_worker import HttpVisualWorker
from sqlalchemy import select
from test_codex_bridge_repository import codex_database, seed  # noqa: F401
from test_codex_candidate_service import codex_policy
from test_codex_model_batch import Readiness
from test_vision_live_persistence import live_browser_worker  # noqa: F401

pytest_plugins = ["vision_trace_fixtures"]


class SyntheticProcess:
    """Windows integration runner; production Linux process-tree behavior is tested separately."""

    def __init__(self, mode, hook):
        self.mode, self.hook, self.calls = mode, hook, []

    async def run(self, request, directory, prompt, stop):
        self.calls.append(request)
        assert (directory / "screenshot.png").exists() == (request.stage == "image")
        self.hook()
        script = Path(__file__).parent / "fixtures/codex_bridge_fake_cli.py"
        # Hard-pin Python + the fixture; no CLI lookup and no auth/provider environment.
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script.resolve()),
            self.mode,
            cwd=directory,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(child.communicate(prompt), timeout=5)
        finally:
            if child.returncode is None:
                child.kill()
                await child.wait()
        assert child.returncode == 0 and not stderr
        reader = EventReader()
        for line in stdout.splitlines():
            reader.event(line)
        output = parse_codex_output((directory / "raw-output.json").read_bytes())
        (directory / "raw-output.json").unlink()
        return BridgeProcessResult(
            output=output, actual_model=reader.actual_model, usage=reader.usage
        )


@pytest.mark.parametrize(
    "variant",
    [
        "dom",
        "image",
        "denied",
        "invalid",
        "revoked",
        "publish_failed",
        "db_failed",
        "stale_binding",
    ],
)
def test_codex_browser_jobs_bindings_and_safe_stops(  # noqa: F811
    codex_database,  # noqa: F811
    live_browser_worker,  # noqa: F811
    tmp_path,
    monkeypatch,
    variant,  # noqa: F811
    on_complete=None,
    allow_generation=False,
):
    policy = codex_policy(
        max_requests_per_minute=10_000,
        raw_screenshot_transfer_accepted=variant == "image",
        raw_screenshot_transfer_provider="codex_cli" if variant == "image" else None,
    )
    factory, scope, uow, store, _ = seed(
        codex_database, target=live_browser_worker["target"], policy=policy
    )
    bridge_id = uuid4()
    spool = FileSpool(tmp_path / "jobs", bridge_id, scope.tenant_id)
    settings = Settings(
        _env_file=None,
        codex_bridge_enabled=True,
        codex_bridge_id=bridge_id,
        codex_bridge_allowed_tenant=scope.tenant_id,
        codex_bridge_host_spool=str(spool.root),
        codex_bridge_container_spool=str(spool.root),
        codex_bridge_executable="/usr/local/bin/codex",
        vision_worker_secret="integration-fixture-only",
        vision_trace_v4_enabled=True,
    )
    with factory.begin() as db:
        db.add(
            ProjectExecutionPolicyModel(
                project_id=scope.project_id,
                tenant_id=scope.tenant_id,
                allowed_origins=[live_browser_worker["target"]] if allow_generation else [],
                vision_max_hops=1,
                vision_max_states=3,
            )
        )
        SqlAlchemyConfigurationRepository(db).set(
            scope.tenant_id,
            AGENT_RUNTIME_CONFIG_KEY,
            {"vision": policy.model_dump(mode="json")},
        )
    monkeypatch.setattr(
        "application.vision_trace_events.decrypt_visual_intent", lambda *_: "fixture"
    )
    if variant == "publish_failed":

        def fail_publish(*_):
            raise OSError("synthetic publication failure")

        monkeypatch.setattr(spool, "publish", fail_publish)
    if variant == "db_failed":
        from infrastructure.persistence.codex_bridge_repository import (
            SqlAlchemyCodexBridgeJobRepository,
        )

        transition = SqlAlchemyCodexBridgeJobRepository.transition

        def fail_completion(self, old, new):
            transition(self, old, new)
            if new.status == "completed":
                raise RuntimeError("synthetic commit failure")

        monkeypatch.setattr(SqlAlchemyCodexBridgeJobRepository, "transition", fail_completion)

    def hook():
        if variant == "revoked":
            with factory.begin() as db:
                changed = policy.model_dump(mode="json") | {"enabled": False}
                SqlAlchemyConfigurationRepository(db).set(
                    scope.tenant_id,
                    AGENT_RUNTIME_CONFIG_KEY,
                    {"vision": changed},
                )

    process = SyntheticProcess(
        "image_branches"
        if variant in {"image", "denied"}
        else "unknown_element"
        if variant == "invalid"
        else "dom_branches",
        hook,
    )
    ready = Readiness()
    bridge = BridgeService(
        settings, spool, process, build_prompt, ready.read(scope.tenant_id, datetime.now(UTC))
    )

    def candidates(lease):
        return CodexCandidateService(
            CodexModelBatch(
                bridge_id=bridge_id,
                spool=spool,
                gateway=SqlAlchemyCodexJobGateway(factory, lease),
                readiness=ready,
                poll_seconds=0.02,
            )
        )

    async def forbidden_http(**_):
        pytest.fail("Codex cannot invoke HTTP/Drive provider fallback")

    async def scenario():
        async def consume():
            while True:
                await bridge.run_once()
                await asyncio.sleep(0.02)

        consumer = asyncio.create_task(consume())
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                worker = HttpVisualWorker(
                    client, live_browser_worker["worker"], settings.vision_worker_secret
                )
                prepare = worker.prepare
                seen = []

                async def verify_binding(command):
                    if command.purpose == "explore":
                        assert command.dom_snapshot_id and command.dom_element_id
                        assert command.expected_locator.value in {"Branch A", "Branch B"}
                        seen.append(command)
                        if variant == "stale_binding" and len(seen) == 2:
                            command = command.model_copy(update={"dom_snapshot_id": uuid4()})
                    return await prepare(command)

                worker.prepare = verify_binding
                processor = VisionTraceEventProcessor(
                    uow, worker, settings, forbidden_http, codex_candidates=candidates
                )
                row = uow.get_session(scope.tenant_id, scope.session_id)
                event = OutboxEvent(
                    id=uuid4(),
                    tenant_id=scope.tenant_id,
                    event_type="agent.visual_exploration.requested.v1",
                    schema_version="v1",
                    correlation_id=row.correlation_id,
                    causation_id=None,
                    idempotency_key="codex-fixture",
                    payload={"session_id": str(scope.session_id)},
                )
                task = asyncio.create_task(processor.execute(event))
                while not process.calls and not task.done():
                    await asyncio.sleep(0.01)
                if not task.done():
                    assert await processor.execute(event) == "busy"
                result = await asyncio.wait_for(task, 30)
                assert await processor.execute(event) == "already_processed"
                if variant in {"dom", "image", "stale_binding"}:
                    assert result == "completed", uow.get_session(
                        scope.tenant_id,
                        scope.session_id,
                    ).safe_failure_reason
                    assert len(seen) == 2
                    assert seen[0].dom_snapshot_id == seen[1].dom_snapshot_id
                else:
                    assert result == "unavailable" and not seen
                # Consumer owns cleanup and exits only after its active child returns.
                await asyncio.sleep(0.1)
        finally:
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)

    asyncio.run(scenario())
    snapshot = uow.read_snapshot(scope)
    success = variant in {"dom", "image", "stale_binding"}
    assert len(snapshot["locators"]) == (1 if variant == "stale_binding" else 2 if success else 0)
    if variant == "stale_binding":
        rejected = [item for item in snapshot["operations"] if item.status == "rejected"]
        assert len(rejected) == 1 and rejected[0].action_kind == "click"
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        assert visits.get("/b", 0) == 0
    with factory() as db:
        jobs = db.scalars(select(CodexBridgeJobModel)).all()
        assert len(jobs) == (2 if variant == "image" else 1)
        assert all(job.status in {"completed", "cancelled", "failed"} for job in jobs)
        proposals = db.scalars(select(VisualActionProposalModel)).all()
        assert len(proposals) == (2 if success else 0)
        assert all(item.target_binding and "text" not in item.action for item in proposals)
        events = db.scalars(select(ActivityEventModel)).all()
        assert any(item.stage == "codex.queued" for item in events)
        assert all("raw-output" not in str(item.event_metadata) for item in events)
    if success:
        assert not spool.jobs()
        assert len(snapshot["handoffs"]) == 1
    assert len(process.calls) == (
        0 if variant == "publish_failed" else 2 if variant == "image" else 1
    )
    if on_complete is not None:
        on_complete(factory, scope, uow, store, settings, process)
