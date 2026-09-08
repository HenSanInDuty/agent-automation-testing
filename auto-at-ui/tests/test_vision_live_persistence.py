"""Real PostgreSQL readers observe each commit while async fixture work is pending."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from application.vision_operations import ExecuteVisualOperation, VisualOperationStopped
from auto_at.contracts.vision_worker import (
    VisualWorkerAction,
    VisualWorkerOperationResult,
    VisualWorkerPrepare,
)
from infrastructure.persistence.repositories import SqlAlchemyVisualTraceRepository
from vision_trace_fixtures import evolve, frame, operation

pytest_plugins = ["vision_trace_fixtures"]
PNG = b"\x89PNG\r\n\x1a\nfixture"


class Worker:
    def __init__(self, intent, *, lose_response=False, lose_browser=False, after_failure=False):
        self.intent = intent
        self.lose_response, self.lose_browser, self.after_failure = (
            lose_response,
            lose_browser,
            after_failure,
        )
        self.executions = 0
        self.acks = []
        self.result = None
        self.before_execute = lambda: None

    async def prepare(self, request):
        before = frame(self.intent, "before", PNG)
        self.result = VisualWorkerOperationResult(
            operation=evolve(self.intent, actual_before_frame_id=before.metadata.id),
            frames=(before.metadata,),
            locator=None,
            prepared_handle=uuid4(),
            state_fingerprint="a" * 64,
            checkpoint=None,
            semantic_change="unavailable",
            duration_ms=0,
            acknowledged=False,
            replayable=False,
        )
        return self.result

    async def execute(self, request):
        self.before_execute()
        self.executions += 1
        assert request.before_persisted is True
        before = self.result.frames[0]
        assert request.before_frame_id == before.id and request.before_checksum == before.checksum
        after = frame(self.intent, "after", PNG)
        final = evolve(
            self.result.operation,
            status="completed",
            ended_at=datetime.now(UTC),
            outcome_code="observed",
            actual_after_frame_id=None if self.after_failure else after.metadata.id,
            after_unavailable_reason="capture_failed" if self.after_failure else None,
        )
        self.result = evolve(
            self.result,
            operation=final,
            frames=(before,) if self.after_failure else (before, after.metadata),
            state_fingerprint="b" * 64,
            semantic_change="changed",
        )
        if self.lose_response:
            raise TimeoutError("synthetic lost response")
        return self.result

    async def read(self, identity, operation_id):
        if self.lose_browser:
            raise ConnectionError("fixture browser lost")
        assert operation_id == self.intent.id
        return self.result

    async def frame(self, identity, metadata):
        return PNG

    async def acknowledge(self, request):
        assert set(request.persisted_frame_ids) == {item.id for item in self.result.frames}
        self.acks.append(request)
        return self.result


def setup(trace_database, **worker_options):
    factory, scope, uow, lease, store = trace_database
    intent = operation(scope, expected_parent_fingerprint="a" * 64)
    worker = Worker(intent, **worker_options)
    service = ExecuteVisualOperation(
        uow,
        worker,
        lease,
        datetime.now(UTC) + timedelta(seconds=30),
        10,
        5000,
        lambda: None,
    )
    request = VisualWorkerPrepare(
        **service.identity.model_dump(),
        operation_id=intent.id,
        purpose="setup",
        action=VisualWorkerAction(kind="navigate"),
        expected_state_fingerprint="a" * 64,
    )
    return factory, scope, uow, store, intent, worker, service, request


def test_independent_connection_reads_before_and_after_while_next_model_waits(trace_database):
    factory, scope, uow, _, intent, worker, service, request = setup(trace_database)

    def verify_before():
        with factory() as reader:
            snapshot = SqlAlchemyVisualTraceRepository(reader).snapshot(scope)
            assert snapshot["operations"][0].status == "executing"
            assert [row.metadata.role for row in snapshot["frames"]] == ["before"]

    worker.before_execute = verify_before

    async def scenario():
        model_waiting, release_model = asyncio.Event(), asyncio.Event()

        async def processor():
            await service.execute(intent, request)
            model_waiting.set()
            await release_model.wait()
            raise RuntimeError("next fixture model failed")

        task = asyncio.create_task(processor())
        await asyncio.wait_for(model_waiting.wait(), timeout=10)
        try:
            with factory() as reader:
                snapshot = SqlAlchemyVisualTraceRepository(reader).snapshot(scope)
                assert snapshot["operations"][0].status == "completed"
                assert {row.metadata.role for row in snapshot["frames"]} == {"before", "after"}
            assert not task.done()
        finally:
            release_model.set()
        with pytest.raises(RuntimeError, match="fixture model failed"):
            await task

    asyncio.run(scenario())
    assert len(uow.read_snapshot(scope)["frames"]) == 2
    assert worker.executions == len(worker.acks) == 1


def test_lost_execute_response_reconciles_without_second_click(trace_database):
    _, scope, uow, _, intent, worker, service, request = setup(trace_database, lose_response=True)
    result = asyncio.run(service.execute(intent, request))
    assert result.operation.status == "completed"
    assert worker.executions == 1
    assert len(uow.read_snapshot(scope)["frames"]) == 2
    result = asyncio.run(service.execute(intent, request))
    assert result.operation.status == "completed" and worker.executions == 1


def test_lost_prepare_response_reads_staged_result_and_does_not_prepare_again(trace_database):
    _, _, _, _, intent, worker, service, request = setup(trace_database)
    prepare = worker.prepare
    attempts = 0

    async def lost_prepare(command):
        nonlocal attempts
        attempts += 1
        await prepare(command)
        raise TimeoutError("fixture prepare reply lost")

    worker.prepare = lost_prepare
    result = asyncio.run(service.execute(intent, request))
    assert result.operation.status == "completed"
    assert attempts == worker.executions == 1


def test_browser_loss_records_unknown_and_redelivery_never_clicks(trace_database):
    _, scope, uow, _, intent, worker, service, request = setup(
        trace_database,
        lose_response=True,
        lose_browser=True,
    )
    with pytest.raises(VisualOperationStopped):
        asyncio.run(service.execute(intent, request))
    saved = uow.read_snapshot(scope)
    assert saved["operations"][0].status == "unknown"
    assert len(saved["frames"]) == 1
    with pytest.raises(VisualOperationStopped):
        asyncio.run(service.execute(intent, request))
    assert worker.executions == 1 and worker.acks == []


def test_failed_before_upload_does_not_dispatch_and_preserves_prior_commit(trace_database):
    _, scope, uow, store, intent, worker, service, request = setup(trace_database)
    store.write_operation_frame = lambda *_: (_ for _ in ()).throw(OSError("upload fixture"))
    with pytest.raises(VisualOperationStopped):
        asyncio.run(service.execute(intent, request))
    saved = uow.read_snapshot(scope)
    assert saved["operations"][0].status == "failed"
    assert not saved["frames"] and worker.executions == 0 and worker.acks == []


def test_failed_after_capture_keeps_real_before_and_explicit_reason(trace_database):
    _, scope, uow, _, intent, worker, service, request = setup(trace_database, after_failure=True)
    result = asyncio.run(service.execute(intent, request))
    assert result.operation.after_unavailable_reason == "capture_failed"
    assert len(uow.read_snapshot(scope)["frames"]) == 1
    assert len(worker.acks) == 1


def test_policy_disabled_after_prepare_prevents_dispatch(trace_database):
    _, scope, uow, _, intent, worker, service, request = setup(trace_database)
    calls = 0

    def policy():
        nonlocal calls
        calls += 1
        if calls > 1:
            raise VisualOperationStopped("policy_disabled")

    service.check_policy = policy
    with pytest.raises(VisualOperationStopped, match="policy_disabled"):
        asyncio.run(service.execute(intent, request))
    assert worker.executions == 0
    assert len(uow.read_snapshot(scope)["frames"]) == 1


def test_deadline_and_operation_budget_stop_before_new_intent(trace_database):
    _, scope, uow, _, intent, worker, service, request = setup(trace_database)
    service.max_operations = 0
    with pytest.raises(VisualOperationStopped, match="operation_budget"):
        asyncio.run(service.execute(intent, request))
    service.deadline = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(VisualOperationStopped, match="session_timeout"):
        asyncio.run(service.execute(intent, request))
    assert not uow.read_snapshot(scope)["operations"] and worker.executions == 0


def test_wrong_worker_result_identity_is_rejected_before_execute(trace_database):
    _, scope, uow, _, intent, worker, service, request = setup(trace_database)
    worker.intent = evolve(intent, id=uuid4())
    with pytest.raises(VisualOperationStopped, match="worker_result_mismatch"):
        asyncio.run(service.execute(intent, request))
    assert worker.executions == 0
    assert uow.read_snapshot(scope)["operations"][0].status == "failed"


def test_unknown_operation_blocks_new_dependent_work(trace_database):
    _, _, _, _, intent, worker, service, request = setup(
        trace_database,
        lose_response=True,
        lose_browser=True,
    )
    with pytest.raises(VisualOperationStopped):
        asyncio.run(service.execute(intent, request))
    next_intent = evolve(intent, id=uuid4(), sequence=2)
    with pytest.raises(VisualOperationStopped, match="previous_operation_unresolved"):
        asyncio.run(service.execute(next_intent, evolve(request, operation_id=next_intent.id)))
    assert worker.executions == 1


def test_cleanup_failure_preserves_final_result_and_can_retry_ack_only(trace_database):
    _, scope, uow, _, intent, worker, service, request = setup(trace_database)
    acknowledge = worker.acknowledge

    async def failed_ack(_request):
        raise ConnectionError("fixture ack lost")

    worker.acknowledge = failed_ack
    with pytest.raises(VisualOperationStopped, match="frame_ack_unavailable"):
        asyncio.run(service.execute(intent, request))
    snapshot = uow.read_snapshot(scope)
    assert snapshot["operations"][0].status == "completed"
    assert len(snapshot["frames"]) == 2
    worker.acknowledge = acknowledge
    result = asyncio.run(service.execute(intent, request))
    assert result.operation.status == "completed" and worker.executions == 1


@pytest.mark.parametrize("browser_lost", [False, True])
def test_expired_owner_recovers_evidence_without_replaying_browser_or_model(
    trace_database, browser_lost
):
    from application.vision_trace_events import VisionTraceEventProcessor
    from auto_at.contracts.vision_worker import VisualWorkerExecute
    from config import Settings
    from domain.runs import OutboxEvent
    from infrastructure.persistence.models import VisualExplorationSessionModel
    from sqlalchemy import update

    factory, scope, uow, _, intent, worker, service, request = setup(trace_database)

    async def dispatched():
        uow.commit_prepared(service.lease, intent)
        prepared = await worker.prepare(request)
        saved = await service._capture(prepared.operation, prepared, "before")
        uow.commit_operation(service.lease, evolve(saved, status="executing"))
        await worker.execute(
            VisualWorkerExecute(
                **service.identity.model_dump(),
                operation_id=intent.id,
                prepared_handle=prepared.prepared_handle,
                before_frame_id=prepared.frames[0].id,
                before_checksum=prepared.frames[0].checksum,
                before_persisted=True,
            )
        )

    asyncio.run(dispatched())
    with factory.begin() as session:
        session.execute(
            update(VisualExplorationSessionModel).values(
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    worker.lose_browser = browser_lost

    async def forbidden_model(**_):
        raise AssertionError("takeover cannot call a model")

    processor = VisionTraceEventProcessor(uow, worker, Settings(_env_file=None), forbidden_model)
    event = OutboxEvent(
        id=uuid4(),
        tenant_id=scope.tenant_id,
        event_type="agent.visual_exploration.requested.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="recovery-fixture",
        payload={"session_id": str(scope.session_id)},
    )
    assert asyncio.run(processor.execute(event)) == "unavailable"
    snapshot = uow.read_snapshot(scope)
    assert snapshot["operations"][0].status == ("unknown" if browser_lost else "completed")
    assert len(snapshot["frames"]) == (1 if browser_lost else 2)
    assert worker.executions == 1
    with pytest.raises(ValueError, match="stale"):
        uow.commit_prepared(service.lease, evolve(intent, id=uuid4(), sequence=2))


@pytest.fixture
def live_browser_worker():
    import json
    import subprocess
    from pathlib import Path

    directory = Path(__file__).parents[1] / "workers" / "playwright"
    process = subprocess.Popen(
        ["node", "--import", "tsx", "src/fixtures/vision-integration-server.ts"],
        cwd=directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    metadata = None
    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as executor:
            metadata = json.loads(executor.submit(process.stdout.readline).result(timeout=20))
        yield metadata
    finally:
        process.terminate()
        process.wait(timeout=10)
        if metadata:
            import shutil
            import tempfile

            owned = Path(metadata["root"]).resolve()
            assert owned.parent == Path(tempfile.gettempdir()).resolve()
            assert owned.name.startswith("vision-integration-")
            shutil.rmtree(owned)


@pytest.mark.parametrize(
    "variant",
    ["branches", "modal", "restore_failed", "cancelled", "model_failed", "generation_failed"],
)
def test_publisher_browser_bfs_commits_live_frames_and_verified_sibling_restore(
    trace_database,
    live_browser_worker,
    monkeypatch,
    variant,
    on_live_commit=None,
):
    import httpx
    from agents.vision.executor import VisualCandidateBatchOutcome
    from application.vision_trace_events import VisionTraceEventProcessor
    from auto_at.contracts.vision import ClickAction, StopAction
    from config import Settings
    from domain.runs import OutboxEvent
    from infrastructure.persistence.models import (
        ProjectExecutionPolicyModel,
        VisualExplorationSessionModel,
    )
    from infrastructure.persistence.repositories import (
        SqlAlchemyOutboxEventRepository,
        SqlAlchemyVisionRepository,
    )
    from infrastructure.vision_worker import HttpVisualWorker
    from infrastructure.workflows.vision_publisher import publish_vision_once
    from sqlalchemy import update

    factory, scope, uow, _, _ = trace_database
    origin = live_browser_worker["target"]
    settings = Settings(
        _env_file=None,
        vision_enabled=True,
        vision_raw_screenshot_transfer_accepted=True,
        vision_model="fixture-model",
        vision_worker_secret="integration-fixture-only",
        vision_max_requests_per_minute=10_000,
        vision_max_steps=3,
        vision_max_session_seconds=60,
        playwright_worker_url=live_browser_worker["worker"],
    )
    with factory.begin() as session:
        session.execute(
            update(VisualExplorationSessionModel).values(
                state="queued",
                lease_owner=None,
                lease_expires_at=None,
                fencing_token=0,
                target_url=origin,
                provider="huggingface",
                model="fixture-model",
                max_requests_per_minute=10_000,
                max_screenshot_bytes=1_000_000,
            )
        )
        session.add(
            ProjectExecutionPolicyModel(
                project_id=scope.project_id,
                tenant_id=scope.tenant_id,
                allowed_origins=[origin],
                vision_max_hops=2,
                vision_max_states=5,
            )
        )
        event = OutboxEvent(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            event_type="agent.visual_exploration.requested.v1",
            schema_version="v1",
            correlation_id=uuid4(),
            causation_id=None,
            idempotency_key="trace-publisher-fixture",
            payload={"session_id": str(scope.session_id)},
        )
        SqlAlchemyOutboxEventRepository(session).append(event)
    monkeypatch.setattr(
        "application.vision_trace_events.decrypt_visual_intent", lambda *_: "fixture"
    )

    async def scenario():
        waiting, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def model(**kwargs):
            nonlocal calls
            calls += 1
            assert kwargs["screenshot"].startswith(b"\x89PNG")
            if calls == 1:
                actions = [
                    ClickAction(x=100 / 1279, y=y / 719, confidence=0.9, expected_outcome="fixture")
                    for y in ((160, 100) if variant == "modal" else (40, 100))
                ]
            else:
                if calls == 2:
                    waiting.set()
                    await release.wait()
                    if variant == "model_failed":
                        return VisualCandidateBatchOutcome(status="unavailable")
                actions = [StopAction(confidence=1, expected_outcome="fixture stop")]
            return VisualCandidateBatchOutcome(status="completed", actions=actions)

        async with httpx.AsyncClient(timeout=10) as client:
            worker = HttpVisualWorker(
                client, settings.playwright_worker_url, settings.vision_worker_secret
            )
            original_checkpoint = worker.checkpoint

            async def checkpoint(identity, checkpoint_id):
                value, matches = await original_checkpoint(identity, checkpoint_id)
                return value, False if variant == "restore_failed" and calls >= 2 else matches

            worker.checkpoint = checkpoint
            handler = VisionTraceEventProcessor(
                uow,
                worker,
                settings,
                model,
            )
            task = asyncio.create_task(publish_vision_once(factory, settings, handler=handler))
            try:
                done, _ = await asyncio.wait(
                    {task, asyncio.create_task(waiting.wait())},
                    timeout=20,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if task in done:
                    await task
                    pytest.fail(
                        str(uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason)
                    )
                assert waiting.is_set()
                with factory() as reader:
                    snapshot = SqlAlchemyVisualTraceRepository(reader).snapshot(scope)
                    assert [op.status for op in snapshot["operations"]] == [
                        "completed",
                        "completed",
                    ]
                    assert len(snapshot["frames"]) == 4
                    assert SqlAlchemyOutboxEventRepository(reader).list_unpublished(100)
                if on_live_commit is not None:
                    on_live_commit()
                if variant == "cancelled":
                    with factory.begin() as writer:
                        writer.execute(
                            update(VisualExplorationSessionModel).values(state="cancelled")
                        )
                release.set()
                assert await asyncio.wait_for(task, timeout=30) == 1
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    record = uow.get_session(scope.tenant_id, scope.session_id)
    snapshot = uow.read_snapshot(scope)
    if variant in {"restore_failed", "cancelled", "model_failed"}:
        assert record.state == ("cancelled" if variant == "cancelled" else "unavailable")
        assert record.safe_failure_reason
        assert len(snapshot["frames"]) >= 4
        assert not any(
            locator.descriptor and locator.descriptor.value == "Branch B"
            for locator in snapshot["locators"]
        )
        with factory() as reader:
            assert not any(
                edge.status == "proposed"
                for edge in SqlAlchemyVisionRepository(reader).list_trajectory_edges(
                    scope.tenant_id, scope.session_id
                )
            )
        return
    assert record.state == "completed", record.safe_failure_reason
    assert [op.action_kind for op in snapshot["operations"]] == [
        "navigate",
        "click",
        "back",
        "navigate" if variant == "modal" else "wait",
        "click",
    ]
    assert [
        locator.descriptor.value
        for locator in sorted(snapshot["locators"], key=lambda x: x.verified_at)
    ] == ["Toggle modal" if variant == "modal" else "Branch A", "Branch B"]
    if variant == "modal":
        assert snapshot["operations"][1].url_change == "unchanged"
        assert snapshot["operations"][3].purpose == "replay"
    with factory() as reader:
        states = SqlAlchemyVisionRepository(reader).list_states(scope.tenant_id, scope.session_id)
        assert len(states) == 3
        edges = SqlAlchemyVisionRepository(reader).list_trajectory_edges(
            scope.tenant_id, scope.session_id
        )
        assert [edge.status for edge in edges].count("observed") == 2
        assert not any(edge.status == "proposed" for edge in edges)

    # Continue from the actual committed handoff/outbox through a selection-only fixture model.
    import json

    from application.generation_events import GenerationEventProcessor
    from infrastructure.persistence.repositories import (
        SqlAlchemyAuditEventRepository,
        SqlAlchemyConfigurationRepository,
        SqlAlchemyGenerationRepository,
    )

    class SelectionModel:
        calls = 0

        async def ainvoke(self, payload, **kwargs):
            self.calls += 1
            if variant == "generation_failed":
                raise RuntimeError("fixture model unavailable")
            context = json.loads(payload["messages"][1]["content"])
            assert "playwright_test_source" not in context["output_schema"]["properties"]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                dict(
                                    title="Observed branches",
                                    selected_branch_ids=[
                                        b["id"]
                                        for b in context["branches"]
                                        if b["status"] == "ready"
                                    ],
                                    assertions=context["allowed_assertions"],
                                )
                            )
                        }
                    }
                ]
            }

    model = SelectionModel()
    monkeypatch.setattr("application.generation_events.create_language_model", lambda *_: model)
    package = snapshot["handoffs"][0]
    assert len(package.branches) == 2
    with factory.begin() as session:
        events = SqlAlchemyOutboxEventRepository(session).list_unpublished(100)
        assert len(events) == 1 and events[0].event_type == "agent.test_generation.requested.v1"
        repository = SqlAlchemyGenerationRepository(session)
        processor = GenerationEventProcessor(
            repository,
            SqlAlchemyConfigurationRepository(session),
            SqlAlchemyAuditEventRepository(session),
            settings,
        )
        expected = "failed" if variant == "generation_failed" else "completed"
        assert asyncio.run(processor.execute(events[0])) == expected
        assert asyncio.run(processor.execute(events[0])) == "already_processed"
        request = repository.get_request(scope.tenant_id, UUID(events[0].payload["request_id"]))
        draft = repository.get_draft_for_request(scope.tenant_id, request.id)
        if expected == "completed":
            assert draft.state == "pending_review" and draft.linked_run_id is None
            assert draft.playwright_test_source.count("test(") == 2
            assert 'name: "Branch B"' in draft.playwright_test_source
            assert draft.provenance["vision_source"]["handoff_hash"] == package.content_hash
            assert draft.provenance["selected_branch_ids"] == [str(b.id) for b in package.branches]
        else:
            assert draft is None and request.failure_reason == "generation unavailable"
    assert model.calls == 1
    assert uow.read_snapshot(scope) == snapshot
