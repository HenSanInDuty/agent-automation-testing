"""Three independent links, including a self-link, need one planning batch."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import test_codex_bridge_repository as database_tests
import test_vision_live_persistence as browser_tests
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY
from agents.vision.codex_service import validate_candidates
from agents.vision.executor import VisualCandidateBatchOutcome
from application.codex_candidates import CodexCandidateService
from application.vision_trace_events import VisionTraceEventProcessor
from auto_at.contracts.codex_bridge import parse_codex_output
from config import Settings
from domain.runs import OutboxEvent
from domain.vision import VisionObservationUnavailable
from infrastructure.persistence.models import (
    ProjectExecutionPolicyModel,
    VisualExplorationSessionModel,
    VisualLocatorHandoffModel,
)
from infrastructure.persistence.repositories import SqlAlchemyConfigurationRepository
from infrastructure.vision_worker import HttpVisualWorker
from sqlalchemy import select
from test_codex_candidate_service import codex_policy

pytest_plugins = ["vision_trace_fixtures"]
codex_database = database_tests.codex_database
live_browser_worker = browser_tests.live_browser_worker


@pytest.mark.parametrize("variant", [
    "hydrate", "persistent", "legacy", "unknown", "page_changed", "state_limit", "hop_limit",
    "refresh_dispatch_once", "refresh_dispatch_persistent", "refresh_dispatch_legacy",
    "refresh_dispatch_unknown", "refresh_dispatch_page_changed", "refresh_dispatch_missing_frame",
    "refresh_dispatch_state_limit", "refresh_dispatch_hop_limit",
    "prepare_once", "prepare_persistent", "prepare_legacy", "prepare_unknown",
    "prepare_page_changed", "prepare_state_limit", "prepare_hop_limit",
])
def test_undispatched_popup_close_observes_same_child_before_new_close(
    codex_database, live_browser_worker, monkeypatch, variant,
):
    target = live_browser_worker["target"] + "/close-race"
    policy = codex_policy(max_requests_per_minute=10_000, max_steps=5)
    factory, scope, uow, _, _ = database_tests.seed(codex_database, target=target, policy=policy)
    with factory.begin() as db:
        row = db.get(VisualExplorationSessionModel, scope.session_id)
        row.max_states, row.max_hops, row.step_timeout_seconds = 20, 10, 60
        db.add(ProjectExecutionPolicyModel(
            project_id=scope.project_id, tenant_id=scope.tenant_id,
            allowed_origins=[live_browser_worker["target"]],
            vision_max_states=20, vision_max_hops=10,
        ))
        SqlAlchemyConfigurationRepository(db).set(
            scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY, {"vision": policy.model_dump(mode="json")},
        )
    monkeypatch.setattr("application.vision_trace_events.decrypt_visual_intent",
                        lambda *_: "Check all buttons")

    class Planner:
        async def propose(self, **kwargs):
            await kwargs["budget"].reserve(evidence_bytes=100)
            bound = kwargs["bound"]
            output = parse_codex_output(json.dumps({"outcome": "candidates", "candidates": [
                {"kind": "click", "element_id": element.element_id, "confidence": .9,
                 "expected_outcome": "Check synthetic button"}
                for element in bound.observation.elements
            ]}).encode())
            return validate_candidates(output, bound, stage="dom", max_candidates=10)

    injected, refresh_injected, requests = [], [], []

    class Worker(HttpVisualWorker):
        async def prepare(self, request):
            requests.append(request)
            prepare_race = (variant.startswith("prepare_")
                            and request.action.kind == "close_popup"
                            and (not injected or variant == "prepare_persistent"))
            if prepare_race:
                async with httpx.AsyncClient() as probe:
                    armed = await probe.get(
                        live_browser_worker["worker"] + "/fixture-arm-close-prepare",
                    )
                    armed.raise_for_status()
            result = await super().prepare(request)
            if prepare_race:
                injected.append(request.operation_id)
                assert result.operation.status == "rejected"
                assert result.operation.outcome_code == "state_changed_during_prepare"
                assert result.dispatch_started is False and result.failure_stage == "prepare"
                assert result.operation.actual_before_frame_id
                assert result.operation.actual_after_frame_id is None
                assert result.operation.after_unavailable_reason == "action_not_executed"
                if variant in {"prepare_state_limit", "prepare_hop_limit"}:
                    with factory.begin() as db:
                        p = db.get(ProjectExecutionPolicyModel, scope.project_id)
                        if variant == "prepare_state_limit":
                            p.vision_max_states = 1
                        else:
                            p.vision_max_hops = 1
                if variant == "prepare_legacy":
                    result = result.model_copy(update={"dispatch_started": None,
                                                       "failure_stage": None})
                if variant == "prepare_unknown":
                    result = result.model_copy(update={"dispatch_started": None,
                        "operation": result.operation.model_copy(update={"status": "unknown"})})
                if variant == "prepare_page_changed":
                    result = result.model_copy(update={"operation": result.operation.model_copy(
                        update={"before_page_id": uuid4()},
                    )})
                return result
            if (request.action.kind == "close_popup" and result.operation.status == "prepared"
                    and (not injected or variant == "persistent")):
                injected.append(request.operation_id)
                mutate = True
            elif (request.refresh_observation and result.operation.status == "prepared"
                  and variant.startswith("refresh_dispatch_")
                  and (not refresh_injected or variant == "refresh_dispatch_persistent")):
                refresh_injected.append(request.operation_id)
                mutate = True
            else:
                mutate = False
            if mutate:
                async with httpx.AsyncClient() as probe:
                    await probe.get(live_browser_worker["target"] + "/close-race-release")
                    for _ in range(100):
                        visits = (await probe.get(
                            live_browser_worker["worker"] + "/fixture-visits",
                        )).json()
                        if visits.get("/close-race-applied/" + str(
                            len(injected) + len(refresh_injected),
                        )):
                            break
                        await asyncio.sleep(.03)
                    else:
                        pytest.fail("popup close barrier not reached")
            return result

        async def execute(self, request):
            result = await super().execute(request)
            if request.operation_id in refresh_injected:
                assert result.operation.status == "rejected"
                assert result.dispatch_started is False
                assert result.failure_stage == "before_dispatch"
                assert result.operation.actual_after_frame_id
                if variant.endswith("_state_limit") or variant.endswith("_hop_limit"):
                    with factory.begin() as db:
                        p = db.get(ProjectExecutionPolicyModel, scope.project_id)
                        if variant.endswith("_state_limit"):
                            p.vision_max_states = 1
                        else:
                            p.vision_max_hops = 1
                if variant == "refresh_dispatch_legacy":
                    return result.model_copy(update={
                        "dispatch_started": None, "failure_stage": None,
                    })
                if variant == "refresh_dispatch_unknown":
                    return result.model_copy(update={"dispatch_started": None,
                        "operation": result.operation.model_copy(update={"status": "unknown"})})
                if variant == "refresh_dispatch_page_changed":
                    return result.model_copy(update={"operation": result.operation.model_copy(
                        update={"after_page_id": uuid4()},
                    )})
                if variant == "refresh_dispatch_missing_frame":
                    return result.model_copy(update={"operation": result.operation.model_copy(
                        update={"actual_after_frame_id": None},
                    )})
            if request.operation_id in injected:
                assert result.operation.status == "rejected"
                assert result.dispatch_started is False
                assert result.failure_stage == "before_dispatch"
                if variant in {"state_limit", "hop_limit"}:
                    with factory.begin() as db:
                        p = db.get(ProjectExecutionPolicyModel, scope.project_id)
                        if variant == "state_limit":
                            p.vision_max_states = 1
                        else:
                            p.vision_max_hops = 1
                if variant == "legacy":
                    return result.model_copy(update={"dispatch_started": None,
                                                     "failure_stage": None})
                if variant == "unknown":
                    return result.model_copy(update={"dispatch_started": None,
                        "failure_stage": None, "operation": result.operation.model_copy(update={
                            "status": "unknown", "outcome_code": "worker_response_lost",
                        })})
                if variant == "page_changed":
                    return result.model_copy(update={"operation": result.operation.model_copy(
                        update={"after_page_id": uuid4()},
                    )})
            return result

    async def scenario():
        settings = Settings(_env_file=None, vision_worker_secret="integration-fixture-only")
        async with httpx.AsyncClient(timeout=20) as client:
            async def forbidden(**_):
                pytest.fail("No live model calls")
            processor = VisionTraceEventProcessor(
                uow, Worker(client, live_browser_worker["worker"], settings.vision_worker_secret),
                settings, forbidden, codex_candidates=lambda _: Planner(),
            )
            return await processor.execute(OutboxEvent(
                id=uuid4(), tenant_id=scope.tenant_id,
                event_type="agent.visual_exploration.requested.v1", schema_version="v1",
                correlation_id=uuid4(), causation_id=None, idempotency_key="popup-close-race",
                payload={"session_id": str(scope.session_id)},
            ))

    state = asyncio.run(scenario())
    operations = uow.read_snapshot(scope)["operations"]
    details = [(op.sequence, op.action_kind, op.status, op.outcome_code) for op in operations]
    recovered = variant in {"hydrate", "refresh_dispatch_once", "prepare_once"}
    assert state == ("completed" if recovered else "unavailable"), details
    assert len(injected) == (3 if variant in {"persistent", "prepare_persistent"} else 1), details
    visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
    assert visits.get("/record-button/popup") == 1
    assert visits.get("/record-button/sibling", 0) == (1 if recovered else 0)
    assert not any(op.purpose == "replay" for op in operations)
    closes = [op for op in operations if op.action_kind == "close_popup"]
    assert sum(op.status == "completed" for op in closes) == (1 if recovered else 0)
    assert closes[0].status == ("unknown" if variant in {"unknown", "prepare_unknown"}
                               else "rejected")
    refreshes = [r for r in requests if r.refresh_observation]
    if variant.startswith("refresh_dispatch_"):
        assert len(refresh_injected) == (3 if variant == "refresh_dispatch_persistent" else 1)
        assert len(refreshes) == (2 if recovered else
                                  3 if variant == "refresh_dispatch_persistent" else 1)
        assert all(r.step_deadline <= refreshes[0].step_deadline for r in refreshes[1:])
        assert all(r.step_deadline <= requests[next(
            i for i, r in enumerate(requests) if r.action.kind == "close_popup"
        )].step_deadline for r in refreshes)
        return
    assert len(refreshes) == (1 if variant in {"hydrate", "prepare_once"} else
                              2 if variant in {"persistent", "prepare_persistent"} else 0)
    close_requests = [r for r in requests if r.action.kind == "close_popup"]
    assert all(r.step_deadline <= close_requests[0].step_deadline for r in close_requests[1:])


@pytest.mark.parametrize("variant", [
    "temporary", "permanent", "form", "state_limit", "hop_limit", "legacy",
])
@pytest.mark.parametrize("stage", ["before_dispatch", "prepare"])
def test_restore_wait_dispatch_race_recovers_only_with_original_checkpoint(
    codex_database, live_browser_worker, monkeypatch, variant, stage,
):
    target = live_browser_worker["target"] + "/restore-race"
    policy = codex_policy(max_requests_per_minute=10_000, max_steps=5)
    factory, scope, uow, _, _ = database_tests.seed(codex_database, target=target, policy=policy)
    with factory.begin() as db:
        row = db.get(VisualExplorationSessionModel, scope.session_id)
        row.max_states, row.max_hops, row.step_timeout_seconds = 20, 10, 60
        db.add(ProjectExecutionPolicyModel(
            project_id=scope.project_id, tenant_id=scope.tenant_id,
            allowed_origins=[live_browser_worker["target"]],
            vision_max_states=20, vision_max_hops=10,
        ))
        SqlAlchemyConfigurationRepository(db).set(
            scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY, {"vision": policy.model_dump(mode="json")},
        )
    monkeypatch.setattr("application.vision_trace_events.decrypt_visual_intent",
                        lambda *_: "Check all buttons")

    class Planner:
        async def propose(self, **kwargs):
            await kwargs["budget"].reserve(evidence_bytes=100)
            bound = kwargs["bound"]
            output = parse_codex_output(json.dumps({"outcome": "candidates", "candidates": [
                {"kind": "click", "element_id": element.element_id, "confidence": .9,
                 "expected_outcome": "Check synthetic button"}
                for element in bound.observation.elements
            ]}).encode())
            return validate_candidates(output, bound, stage="dom", max_candidates=10)

    injected = []
    requests = []

    async def barrier(action, expected):
        async with httpx.AsyncClient() as probe:
            await probe.get(live_browser_worker["target"] + "/restore-race-" + action)
            for _ in range(100):
                visits = (await probe.get(live_browser_worker["worker"] + "/fixture-visits")).json()
                if visits.get("/restore-race-applied/" + expected):
                    return
                await asyncio.sleep(.03)
            pytest.fail("restore race barrier not reached")

    class Worker(HttpVisualWorker):
        async def prepare(self, request):
            requests.append(request)
            preparing = (stage == "prepare" and not injected
                         and request.action.kind == "wait" and request.purpose == "restore")
            if preparing:
                async with httpx.AsyncClient() as probe:
                    armed = await probe.get(live_browser_worker["worker"]
                        + "/fixture-arm-restore-prepare/"
                        + ("form" if variant == "form" else "changed"))
                    armed.raise_for_status()
            result = await super().prepare(request)
            if preparing:
                injected.append(request.operation_id)
                assert result.operation.status == "rejected"
                assert result.operation.outcome_code == "state_changed_during_prepare"
                assert result.dispatch_started is False and result.failure_stage == "prepare"
                if variant in {"temporary", "state_limit", "hop_limit", "legacy"}:
                    await barrier("reset", "stable")
                if variant in {"state_limit", "hop_limit"}:
                    with factory.begin() as db:
                        p = db.get(ProjectExecutionPolicyModel, scope.project_id)
                        if variant == "state_limit":
                            p.vision_max_states = 1
                        else:
                            p.vision_max_hops = 1
                if variant == "legacy":
                    result = result.model_copy(update={"dispatch_started": None,
                                                       "failure_stage": None})
                return result
            if (not injected and request.action.kind == "wait" and request.purpose == "restore"
                    and result.operation.status == "prepared"):
                injected.append(request.operation_id)
                await barrier("form" if variant == "form" else "release",
                              "form" if variant == "form" else "changed")
            return result

        async def execute(self, request):
            result = await super().execute(request)
            if stage == "before_dispatch" and injected and request.operation_id == injected[0]:
                assert result.operation.status == "rejected"
                assert result.operation.outcome_code == "state_mismatch"
                if variant in {"temporary", "state_limit", "hop_limit", "legacy"}:
                    await barrier("reset", "stable")
                if variant == "state_limit":
                    with factory.begin() as db:
                        db.get(ProjectExecutionPolicyModel, scope.project_id).vision_max_states = 1
                if variant == "hop_limit":
                    with factory.begin() as db:
                        db.get(ProjectExecutionPolicyModel, scope.project_id).vision_max_hops = 1
                if variant == "legacy":
                    return result.model_copy(update={"dispatch_started": None,
                                                     "failure_stage": None})
            return result

    async def scenario():
        settings = Settings(_env_file=None, vision_worker_secret="integration-fixture-only")
        async with httpx.AsyncClient(timeout=20) as client:
            async def forbidden(**_):
                pytest.fail("No live model calls")
            processor = VisionTraceEventProcessor(
                uow, Worker(client, live_browser_worker["worker"], settings.vision_worker_secret),
                settings, forbidden, codex_candidates=lambda _: Planner(),
            )
            return await processor.execute(OutboxEvent(
                id=uuid4(), tenant_id=scope.tenant_id,
                event_type="agent.visual_exploration.requested.v1", schema_version="v1",
                correlation_id=uuid4(), causation_id=None, idempotency_key="restore-race",
                payload={"session_id": str(scope.session_id)},
            ))

    state = asyncio.run(scenario())
    record = uow.get_session(scope.tenant_id, scope.session_id)
    operations = uow.read_snapshot(scope)["operations"]
    details = (record.safe_failure_reason,
               [(op.sequence, op.action_kind, op.status, op.outcome_code) for op in operations])
    assert len(injected) == 1, details
    assert state == ("completed" if variant == "temporary" else "unavailable"), details
    visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
    assert visits.get("/record-button/popup") == 1
    assert visits.get("/record-button/sibling", 0) == (1 if variant == "temporary" else 0)
    rejected = next(op for op in operations if op.id == injected[0])
    assert rejected.status == "rejected" and rejected.actual_before_frame_id
    assert bool(rejected.actual_after_frame_id) == (stage == "before_dispatch")
    assert not any(op.purpose == "replay" for op in operations)
    later = [op for op in operations if op.sequence > rejected.sequence]
    refreshes = [op for op in later if op.action_kind == "wait" and op.purpose == "setup"]
    assert len(refreshes) == (1 if variant == "temporary" else
                              2 if variant in {"permanent", "form"} else 0), details
    if variant == "temporary":
        verification = [r for r in requests if r.restore_checkpoint_id and r.action.kind == "wait"]
        assert len(verification) >= 2
        assert verification[0].restore_checkpoint_id == verification[1].restore_checkpoint_id
        assert verification[1].step_deadline <= verification[0].step_deadline


@pytest.mark.parametrize("dom_error", [
    None, "state_mismatch", "once", "step_timeout_mode", "pre_model_once", "pre_model_always",
    "post_model_stale", "post_model_revalidate", "post_model_reject", "refresh_timeout",
    "action_capture_failed", "refresh_prepare_once", "refresh_prepare_always",
    "refresh_prepare_legacy",
])
def test_page_batch_exhausts_siblings_saves_urls_and_never_repeats_home(
    codex_database, live_browser_worker, monkeypatch, dom_error,
):
    target = live_browser_worker["target"] + "/page-inventory"
    policy = codex_policy(max_requests_per_minute=10_000)
    factory, scope, uow, _, _ = database_tests.seed(codex_database, target=target, policy=policy)
    with factory.begin() as db:
        if dom_error == "step_timeout_mode" or str(dom_error).startswith("refresh_prepare_"):
            db.get(VisualExplorationSessionModel, scope.session_id).step_timeout_seconds = 120
        db.add(ProjectExecutionPolicyModel(project_id=scope.project_id, tenant_id=scope.tenant_id,
                                          allowed_origins=[live_browser_worker["target"]],
                                          vision_max_hops=5, vision_max_states=8))
        if dom_error in {"post_model_revalidate", "post_model_reject"}:
            row = db.get(VisualExplorationSessionModel, scope.session_id)
            row.max_hops, row.max_states = 5, 8
        SqlAlchemyConfigurationRepository(db).set(scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY,
                                                  {"vision": policy.model_dump(mode="json")})
    monkeypatch.setattr("application.vision_trace_events.decrypt_visual_intent",
                        lambda *_: "Explore all three links")
    if dom_error == "step_timeout_mode":
        running = uow.running

        def aged_running(*args):
            row = running(*args)
            # The session is older than the former total budget before any work;
            # every new browser/model step must still receive its own deadline.
            row.updated_at -= timedelta(minutes=10)
            return row

        monkeypatch.setattr(uow, "running", aged_running)
    calls = []
    planner_attempts = []
    class Planner:
        async def propose(self, **kwargs):
            planner_attempts.append(kwargs["bound"].observation.snapshot_id)
            if (dom_error in {"pre_model_once", "pre_model_always"}
                    and not await kwargs["check_state"]()):
                return VisualCandidateBatchOutcome(
                    status="unavailable", failure_reason="bridge_stale_result", calls_used=0,
                )
            if dom_error == "step_timeout_mode":
                from datetime import UTC, datetime
                assert (kwargs["budget"].deadline - datetime.now(UTC)).total_seconds() > 100
            calls.append(kwargs)
            if dom_error not in {"post_model_revalidate", "post_model_reject"}:
                await kwargs["budget"].reserve(evidence_bytes=100)
            if dom_error == "post_model_stale":
                return VisualCandidateBatchOutcome(
                    status="unavailable", failure_reason="bridge_stale_result", calls_used=1,
                )
            bound = kwargs["bound"]
            assert [e.name for e in bound.observation.elements] == ["Home", "News", "Events"]
            output = parse_codex_output(json.dumps({"outcome": "candidates", "candidates": [
                {"kind": "click", "element_id": element.element_id, "confidence": .9,
                 "expected_outcome": "Explore synthetic link"}
                for element in bound.observation.elements[:10]
            ]}).encode())
            if dom_error in {"post_model_revalidate", "post_model_reject"}:
                async def exchange(**_):
                    return SimpleNamespace(output=output, failure_code=None)
                return await CodexCandidateService(exchange).propose(**kwargs)
            return validate_candidates(output, bound, stage="dom", max_candidates=10)

    async def forbidden(**_):
        pytest.fail("No HTTP model fallback")

    class Worker(HttpVisualWorker):
        observations = 0
        stale_once = False
        state_checks = 0

        async def execute(self, request):
            result = await super().execute(request)
            if dom_error == "action_capture_failed" and result.operation.action_kind == "click":
                self.capture_remote_frames = tuple(frame.id for frame in result.frames)
                self.capture_operation_id = result.operation.id
                return result.model_copy(update={
                    "operation": result.operation.model_copy(update={
                        "actual_after_frame_id": None, "after_unavailable_reason": "capture_failed",
                    }),
                    "frames": tuple(frame for frame in result.frames if frame.role == "before"),
                    "checkpoint": None,
                })
            return result

        async def prepare(self, request):
            refresh_race = str(dom_error).startswith("refresh_prepare_")
            if request.refresh_observation and (dom_error == "refresh_timeout" or (
                refresh_race and (dom_error != "refresh_prepare_once"
                                 or not getattr(self, "refresh_rejections", []))
            )):
                # Reject before dispatch, preserving a typed safe worker reason.
                from auto_at.contracts.vision import VisualOperation
                from auto_at.contracts.vision_worker import VisualWorkerOperationResult

                now = datetime.now(UTC)
                self.rejected_refresh_id = request.operation_id
                self.refresh_rejections = getattr(self, "refresh_rejections", [])
                if refresh_race and self.refresh_rejections:
                    assert request.step_deadline <= self.refresh_rejections[0].step_deadline
                self.refresh_rejections.append(request)
                code = "state_changed_during_prepare" if refresh_race else "settle_timeout"
                if refresh_race:
                    # Real capture barrier: preparation rejects after persisting
                    # its before-frame, with explicit positive no-dispatch proof.
                    async with httpx.AsyncClient() as probe:
                        armed = await probe.get(live_browser_worker["worker"]
                                                + "/fixture-arm-refresh-prepare")
                        armed.raise_for_status()
                    rejected = await super().prepare(request)
                    assert rejected.operation.status == "rejected"
                    assert rejected.operation.actual_before_frame_id
                    assert rejected.operation.outcome_code == code
                    assert rejected.dispatch_started is False
                    async with httpx.AsyncClient() as probe:
                        reset = await probe.get(live_browser_worker["worker"]
                                                + "/fixture-reset-refresh-prepare")
                        reset.raise_for_status()
                    return rejected.model_copy(update={
                        "dispatch_started": (
                            None if dom_error == "refresh_prepare_legacy" else False),
                        "failure_stage": (
                            None if dom_error == "refresh_prepare_legacy" else "prepare"),
                    })
                return VisualWorkerOperationResult(
                    operation=VisualOperation(
                        id=request.operation_id, tenant_id=request.tenant_id,
                        project_id=request.project_id, session_id=request.session_id,
                        sequence=2, purpose=request.purpose, action_kind=request.action.kind,
                        state_id=request.state_id, proposal_id=request.proposal_id,
                        parent_operation_id=self.last_operation_id,
                        expected_parent_fingerprint=request.expected_state_fingerprint,
                        status="rejected", outcome_code=code,
                        started_at=now, ended_at=now,
                        before_page_id=getattr(self, "last_page_id", None),
                        before_unavailable_reason=code,
                        after_unavailable_reason="action_not_executed",
                    ),
                    frames=(), locator=None, prepared_handle=uuid4(), state_fingerprint=None,
                    checkpoint=None, semantic_change="unavailable", duration_ms=0,
                    acknowledged=False, replayable=False,
                )
            if request.refresh_observation and getattr(self, "refresh_rejections", []):
                assert request.step_deadline <= self.refresh_rejections[0].step_deadline
            result = await super().prepare(request)
            self.last_operation_id = result.operation.id
            self.last_page_id = result.operation.before_page_id
            return result

        async def acknowledge(self, request):
            if request.operation_id == getattr(self, "capture_operation_id", None):
                request = request.model_copy(update={
                    "persisted_frame_ids": self.capture_remote_frames,
                })
            if request.operation_id == getattr(self, "rejected_refresh_id", None):
                return None
            return await super().acknowledge(request)

        async def checkpoint(self, *args):
            checkpoint, matches = await super().checkpoint(*args)
            self.state_checks += 1
            if (dom_error in {"post_model_revalidate", "post_model_reject"}
                    and self.state_checks == 4):
                return checkpoint, False
            if dom_error == "pre_model_always" and self.observations:
                return checkpoint, False
            if dom_error == "pre_model_once" and self.observations and not self.stale_once:
                self.stale_once = True
                return checkpoint, False
            return checkpoint, matches

        async def observe_dom(self, request):
            self.observations += 1
            if dom_error == "post_model_reject" and request.revalidate_snapshot_id:
                raise VisionObservationUnavailable("stale_dom_context")
            if dom_error in {"state_mismatch", "refresh_timeout"} or (
                dom_error == "once" and self.observations == 1
            ) or (
                str(dom_error).startswith("refresh_prepare_") and self.observations == 1
            ):
                raise VisionObservationUnavailable("state_mismatch")
            return await super().observe_dom(request)

    async def scenario():
        settings = Settings(_env_file=None, vision_worker_secret="integration-fixture-only")
        async with httpx.AsyncClient(timeout=10) as client:
            processor = VisionTraceEventProcessor(
                uow, Worker(client, live_browser_worker["worker"],
                                     settings.vision_worker_secret), settings, forbidden,
                codex_candidates=lambda _: Planner(),
            )
            row = uow.get_session(scope.tenant_id, scope.session_id)
            event = OutboxEvent(id=uuid4(), tenant_id=scope.tenant_id,
                                event_type="agent.visual_exploration.requested.v1",
                                schema_version="v1", correlation_id=row.correlation_id,
                                causation_id=None, idempotency_key="page-batch",
                                payload={"session_id": str(scope.session_id)})
            result = await processor.execute(event)
            assert result == (
                "unavailable" if dom_error in {
                    "state_mismatch", "post_model_stale", "post_model_reject", "pre_model_always",
                    "refresh_timeout", "action_capture_failed", "refresh_prepare_always",
                    "refresh_prepare_legacy",
                }
                else "completed"
            ), (uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason,
                [(op.action_kind, op.status, op.outcome_code)
                 for op in uow.read_snapshot(scope)["operations"]])
    asyncio.run(scenario())
    snapshot = uow.read_snapshot(scope)
    if str(dom_error).startswith("refresh_prepare_"):
        rejected = [op for op in snapshot["operations"] if op.status == "rejected"]
        assert len(rejected) == (3 if dom_error == "refresh_prepare_always" else 1), [
            (op.sequence, op.purpose, op.action_kind, op.outcome_code) for op in rejected
        ]
        assert all(op.action_kind == "wait" and op.purpose == "setup"
                   and op.outcome_code == "state_changed_during_prepare" for op in rejected)
        assert not any(op.purpose == "replay" for op in snapshot["operations"])
        if dom_error != "refresh_prepare_once":
            assert not calls and not snapshot["locators"]
            return
    if dom_error == "action_capture_failed":
        assert uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason == (
            "capture_failed"
        )
        clicks = [op for op in snapshot["operations"] if op.action_kind == "click"]
        assert len(clicks) == 1 and clicks[0].status == "completed" and clicks[0].executed_click
        assert clicks[0].outcome_code == "observed" and clicks[0].actual_after_frame_id is None
        assert clicks[0].after_unavailable_reason == "capture_failed"
        return
    if dom_error in {"post_model_stale", "post_model_reject", "pre_model_always"}:
        assert len(planner_attempts) == (3 if dom_error == "pre_model_always" else 1)
        assert sum(op.purpose == "setup" and op.action_kind == "wait"
                   for op in snapshot["operations"]) == (
                        0 if dom_error == "post_model_stale" else
                        1 if dom_error == "post_model_reject" else 2
                   )
        assert not snapshot["locators"]
        assert not any(op.action_kind == "click" for op in snapshot["operations"])
        assert uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason == (
            "bridge_stale_result"
        )
        return
    if dom_error == "pre_model_once":
        assert len(planner_attempts) == 2 and len(set(planner_attempts)) == 2
    if dom_error in {"state_mismatch", "refresh_timeout"}:
        assert not calls and not snapshot["locators"] and not snapshot["pages"]
        assert uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason == (
            "settle_timeout" if dom_error == "refresh_timeout" else dom_error
        )
        return
    clicks = [op for op in snapshot["operations"] if op.purpose == "explore"]
    assert len(calls) == 1 and len(clicks) == 3
    assert all(op.status == "completed" and op.executed_click for op in clicks)
    assert {locator.descriptor.value for locator in snapshot["locators"]} == {
        "Home", "News", "Events",
    }
    pages = snapshot["pages"]
    assert pages[0].page_url == target and len(pages[0].controls) == 3
    assert all(control.status == "completed" for control in pages[0].controls)
    assert {page.page_url for page in pages} == {
        target, live_browser_worker["target"] + "/a", live_browser_worker["target"] + "/b",
    }
    if dom_error in {"once", "pre_model_once", "post_model_revalidate", "refresh_prepare_once"}:
        assert any(op.purpose == "setup" and op.action_kind == "wait"
                   and op.status == "completed" for op in snapshot["operations"])
    else:
        assert any(op.purpose == "restore" and op.action_kind == "navigate"
                   for op in snapshot["operations"])


@pytest.mark.parametrize("variant", [
    "popup_refresh", "scroll", "call_limit", "buttons", "button_tabs", "anonymous",
    "visual_dataset", "visual_navigation", "visual_navigation_drift", "visual_question",
    "visual_compact_scan", "visual_noop_replacement", "visual_deep_twenty", "visual_deep_ten",
    "visual_mutation_queue", "visual_mutation_queue_form", "visual_mutation_queue_limit",
    "visual_panel_order",
    "visual_noop_batch", "visual_delayed", "visual_empty",
])
def test_restored_tabs_and_viewport_coverage_keep_verified_targets(
    codex_database, live_browser_worker, monkeypatch, variant,
):
    path = ("/coverage-panel-order" if variant == "visual_panel_order" else
            "/coverage-mutation-queue-form" if variant == "visual_mutation_queue_form" else
            "/coverage-mutation-queue" if variant.startswith("visual_mutation_queue") else
            "/coverage-deep-tabs" if variant.startswith("visual_deep_") else
            "/coverage-visual-empty" if variant == "visual_empty" else
            "/coverage-visual-delayed" if variant == "visual_delayed" else
            "/coverage-visual-noop-batch" if variant == "visual_noop_batch" else
            "/visual-buttons-navigation-drift" if variant == "visual_navigation_drift" else
            "/visual-buttons-navigation" if variant == "visual_navigation" else
            "/visual-buttons-dataset" if variant == "visual_dataset" else
            "/coverage-compact-scan" if variant == "visual_compact_scan" else
            "/coverage-visual-noop-replacement" if variant == "visual_noop_replacement" else
            "/coverage-popup" if variant == "popup_refresh" else
            "/coverage-anonymous-buttons" if variant == "anonymous" else
            "/coverage-button-tabs" if variant == "button_tabs" else
            "/coverage-buttons" if variant in {"buttons", "visual_question"}
            else "/coverage-scroll")
    target = live_browser_worker["target"] + path
    policy = codex_policy(max_requests_per_minute=10_000,
                         max_steps=(20 if variant in {"visual_dataset", "visual_compact_scan",
                                                     "visual_deep_twenty", "visual_deep_ten"} else
                                    1 if variant in {"call_limit", "visual_mutation_queue_limit"}
                                    else 5))
    factory, scope, uow, _, _ = database_tests.seed(codex_database, target=target, policy=policy)
    with factory.begin() as db:
        row = db.get(VisualExplorationSessionModel, scope.session_id)
        row.max_states, row.max_hops, row.step_timeout_seconds = (
            (100, 20, 120) if variant == "visual_deep_twenty" else
            (100, 10, 120) if variant == "visual_deep_ten" else
            (200, 10, 120) if variant == "visual_dataset" else
            (50, 10, 120) if variant == "visual_compact_scan" else (15, 5, 60)
        )
        db.add(ProjectExecutionPolicyModel(project_id=scope.project_id, tenant_id=scope.tenant_id,
                                          allowed_origins=[live_browser_worker["target"]],
                                          vision_max_hops=row.max_hops,
                                          vision_max_states=row.max_states))
        SqlAlchemyConfigurationRepository(db).set(scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY,
                                                  {"vision": policy.model_dump(mode="json")})
    monkeypatch.setattr("application.vision_trace_events.decrypt_visual_intent",
                        lambda *_: "Kiểm tra các nút xem có hoạt động không"
                        if variant == "visual_question" else "Kiểm tra các nút"
                        if variant in { "buttons", "button_tabs", "anonymous", "visual_dataset",
                           "visual_navigation", "visual_navigation_drift", "visual_noop_batch",
                           "visual_delayed", "visual_empty", "visual_compact_scan",
                           "visual_noop_replacement", "visual_deep_twenty", "visual_deep_ten",
                           "visual_mutation_queue", "visual_mutation_queue_form",
                           "visual_mutation_queue_limit", "visual_panel_order" }
                        else
                        "Explore the visible and lower-page links")
    # Retain regression coverage for explicitly requested legacy semantic scope.
    if variant in {"buttons", "button_tabs", "anonymous"}:
        monkeypatch.setattr("application.vision_trace_events.interaction_scope",
                            lambda _: "buttons")
    calls = []
    preflight_checks = []

    class Planner:
        async def propose(self, **kwargs):
            await kwargs["budget"].reserve(evidence_bytes=100)
            bound = kwargs["bound"]
            calls.append([e.name for e in bound.observation.elements])
            output = parse_codex_output(json.dumps({"outcome": "candidates", "candidates": [
                {"kind": "click", "element_id": element.element_id, "confidence": .9,
                 "expected_outcome": "Open synthetic content"}
                for element in bound.observation.elements[:10]
            ]}).encode())
            return validate_candidates(output, bound, stage="dom", max_candidates=10)

    class Worker(HttpVisualWorker):
        observations = 0

        async def check_target(self, request):
            result = await super().check_target(request)
            preflight_checks.append((result.matches_current, result.context_matches,
                                     result.same_document, request.allow_restored_document))
            return result

        async def execute(self, request):
            result = await super().execute(request)
            op = result.operation
            if (variant == "visual_navigation_drift" and op.action_kind == "click"
                    and op.before_page_id != op.after_page_id):
                async with httpx.AsyncClient() as probe:
                    await probe.get(live_browser_worker["target"] + "/popup-release")
                    for _ in range(100):
                        visits = (await probe.get(
                            live_browser_worker["worker"] + "/fixture-visits"
                        )).json()
                        if visits.get("/popup-hydrated"):
                            break
                        await asyncio.sleep(.05)
                    else:
                        pytest.fail("popup hydration did not complete")
            return result

        async def observe_dom(self, request):
            self.observations += 1
            if variant == "popup_refresh" and self.observations == 2:
                raise VisionObservationUnavailable("state_mismatch")
            result = await super().observe_dom(request)
            if variant == "visual_delayed" and self.observations == 1:
                assert result.data.observation.elements == ()
                async with httpx.AsyncClient() as probe:
                    await probe.get(live_browser_worker["target"] + "/initial-release")
                    for _ in range(100):
                        visits = (await probe.get(
                            live_browser_worker["worker"] + "/fixture-visits"
                        )).json()
                        if visits.get("/initial-hydrated"):
                            break
                        await asyncio.sleep(.05)
                    else:
                        pytest.fail("initial hydration did not complete")
            return result

    async def scenario():
        settings = Settings(_env_file=None, vision_worker_secret="integration-fixture-only")
        async with httpx.AsyncClient(timeout=20) as client:
            async def forbidden(**_):
                pytest.fail("No live model calls")
            processor = VisionTraceEventProcessor(
                uow, Worker(client, live_browser_worker["worker"], settings.vision_worker_secret),
                settings, forbidden, codex_candidates=lambda _: Planner(),
            )
            event = OutboxEvent(id=uuid4(), tenant_id=scope.tenant_id,
                               event_type="agent.visual_exploration.requested.v1",
                               schema_version="v1", correlation_id=uuid4(), causation_id=None,
                               idempotency_key="coverage-regression",
                               payload={"session_id": str(scope.session_id)})
            result = await processor.execute(event)
            record = uow.get_session(scope.tenant_id, scope.session_id)
            assert result == ("unavailable" if variant in {
                "call_limit", "visual_empty", "visual_deep_ten",
                "visual_mutation_queue_limit",
            }
                              else "completed"), (
                record.safe_failure_reason, [(o.sequence, o.outcome_code)
                                            for o in uow.read_snapshot(scope)["operations"]],
                preflight_checks,
            )
            if variant == "call_limit":
                assert record.safe_failure_reason == "exploration_call_limit"
    asyncio.run(scenario())
    snapshot = uow.read_snapshot(scope)
    operations = snapshot["operations"]
    assert not any(o.outcome_code == "stale_dom_snapshot" for o in operations)
    names = {locator.descriptor.value for locator in snapshot["locators"]}
    if variant == "visual_panel_order":
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        assert {path: count for path, count in visits.items()
                if path.startswith("/record-button/")} == {
            "/record-button/current-tab": 1, "/record-button/other-tab": 1,
            "/record-button/child-one": 1, "/record-button/child-two": 1,
        }
        assert calls == [["Current tab", "Other tab", "Child one", "Child two", "Destination"]]
        assert all(op.status == "completed" for op in operations)
        clicks = [op for op in operations if op.action_kind == "click"]
        assert len(clicks) == 5 and clicks[0].url_change == "changed"
        assert not any(op.purpose == "replay" for op in operations)
        assert [path for path in visits if path.startswith("/record-button/")] == [
            "/record-button/child-one", "/record-button/child-two",
            "/record-button/current-tab", "/record-button/other-tab",
        ]
    elif variant.startswith("visual_mutation_queue"):
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        limited = variant == "visual_mutation_queue_limit"
        assert visits.get("/record-button/tab-a") == 1
        assert visits.get("/record-button/tab-b", 0) == (0 if limited else 1)
        assert calls == ([["Tab A", "Tab B"]] if limited else [["Tab A", "Tab B"], ["Tab B"]])
        assert not any(op.action_kind == "back" or op.purpose == "replay" for op in operations)
        assert all(op.status == "completed" for op in operations)
        from infrastructure.persistence.repositories import SqlAlchemyVisionRepository
        with factory() as db:
            edges = SqlAlchemyVisionRepository(db).list_trajectory_edges(
                scope.tenant_id, scope.session_id,
            )
        superseded = [edge for edge in edges if edge.outcome_code == "stale_dom_context"]
        assert len(superseded) == 1 and superseded[0].status == "terminal"
        assert all(op.proposal_id != superseded[0].proposal_id for op in operations)
        if limited:
            assert uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason == (
                "exploration_call_limit"
            )
    elif variant.startswith("visual_deep_"):
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        count = 12 if variant == "visual_deep_twenty" else 10
        assert {key: value for key, value in visits.items()
                if key.startswith("/record-button/deep-")} == {
                    f"/record-button/deep-{i}": 1 for i in range(count)
                }
        assert len(calls) == count
        assert all(op.status == "completed" and op.purpose != "replay" for op in operations)
        with factory() as db:
            from infrastructure.persistence.models import VisualExplorationStateModel
            states = list(db.scalars(select(VisualExplorationStateModel).where(
                VisualExplorationStateModel.session_id == scope.session_id,
            )))
            assert max(state.hop for state in states) == count
    elif variant == "visual_noop_replacement":
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        assert visits.get("/record-button/noop-0") == 1
        assert visits.get("/record-button/noop-1", 0) == 1
        assert len(calls) == 3  # two original batches and a new proposal for stale siblings
        from infrastructure.persistence.repositories import SqlAlchemyVisionRepository
        with factory() as db:
            edges = SqlAlchemyVisionRepository(db).list_trajectory_edges(
                scope.tenant_id, scope.session_id,
            )
        superseded = [edge for edge in edges if edge.outcome_code == "stale_dom_context"]
        assert superseded and all(edge.status == "terminal" for edge in superseded)
        assert not any(op.proposal_id in {edge.proposal_id for edge in superseded}
                       for op in operations)
        assert all(op.status == "completed" for op in operations)
        assert not any(op.purpose == "replay" for op in operations)
    elif variant == "visual_compact_scan":
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        clicked = {name: count for name, count in visits.items()
                   if name.startswith("/record-button/compact-")}
        assert clicked == {f"/record-button/compact-{i}": 1 for i in range(45)}
        assert all(op.status == "completed" for op in operations)
        with factory() as db:
            from infrastructure.persistence.models import VisualExplorationStateModel
            states = list(db.scalars(select(VisualExplorationStateModel).where(
                VisualExplorationStateModel.session_id == scope.session_id,
            )))
            assert len(states) <= 50 and max(s.hop for s in states) <= 10
    elif variant == "visual_dataset":
        from pathlib import Path

        data = json.loads(Path("benchmark/vision/visual-buttons/mongchiton-desktop.json")
                          .read_text(encoding="utf-8"))
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        clicked = {path.removeprefix("/record-button/"): count
                   for path, count in visits.items() if path.startswith("/record-button/")}
        expected = {e["id"]: 1 for e in data["examples"] if e["expected"]}
        assert clicked == expected
        assert len(names) == 47
        assert all(op.status == "completed" for op in operations)
        assert len([op for op in operations if op.action_kind == "click"]) == 47
        first_click = next(op.sequence for op in operations if op.action_kind == "click")
        assert sum(op.sequence < first_click and op.action_kind == "scroll"
                   for op in operations) > 0
        assert all(item.executed_click for item in operations if item.action_kind == "click")
        Path("benchmark/vision/visual-buttons/flow-result.json").write_text(json.dumps({
            "schema_version": "visual-button-flow-evaluation-v1",
            "environment": "isolated_local_fixture", "live_model_calls": 0,
            "expected_clicks": 47, "confirmed_clicks": len(clicked),
            "negative_targets_clicked": 0, "operations": len(operations),
            "model_batches": len(calls), "state": "completed",
        }, indent=2) + "\n", encoding="utf-8")
    elif variant == "visual_empty":
        assert uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason \
            == "exploration_coverage_incomplete"
        assert calls == []
        assert [op.action_kind for op in operations] == ["navigate", "wait", "wait"]
        assert all(op.status == "completed" and op.actual_after_frame_id for op in operations)
    elif variant == "visual_delayed":
        assert calls == [["Late button"]]
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        assert visits["/record-button/late"] == 1
        clicked = [op for op in operations if op.action_kind == "click"]
        assert len(clicked) == 1 and clicked[0].status == "completed"
        assert any(op.action_kind == "wait" and op.purpose == "setup"
                   and op.sequence < clicked[0].sequence for op in operations)
    elif variant == "visual_noop_batch":
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        assert {path: count for path, count in visits.items()
                if path.startswith("/record-button/")} == {
            f"/record-button/noop-{index}": 1 for index in range(12)
        }
        assert len(names) == 12
        assert all(op.status == "completed" for op in operations)
        assert len([op for op in operations if op.action_kind == "click"]) == 12
        assert not any(op.purpose == "replay" for op in operations)
    elif variant in {"visual_navigation", "visual_navigation_drift"}:
        assert len(names) == 4
        assert all(op.status == "completed" for op in operations)
        assert {page.page_url for page in snapshot["pages"]} == {target}
        assert any(op.action_kind == "close_popup" for op in operations)
        # The popup precedes a pending sibling, so restoration is necessary.
        # A popup clicked last is closed by session cleanup, not a restore action.
        popup = next(op for op in operations if op.action_kind == "click"
                     and op.before_page_id != op.after_page_id)
        closed = next(op for op in operations if op.action_kind == "close_popup")
        assert closed.sequence > popup.sequence
        assert closed.before_page_id == popup.after_page_id
        assert closed.after_page_id == popup.before_page_id
        assert any(op.action_kind == "click" and op.sequence > closed.sequence
                   and op.before_page_id == popup.before_page_id for op in operations)
        if variant == "visual_navigation_drift":
            assert any(op.action_kind == "wait" and op.purpose == "setup"
                       and popup.sequence < op.sequence < closed.sequence
                       and op.before_page_id == popup.after_page_id
                       and op.after_page_id == popup.after_page_id for op in operations)
    elif variant == "anonymous":
        assert calls == [[""], [""]]
        assert len(snapshot["locators"]) == 2
        assert all(item.descriptor.strategy == "dom_path" for item in snapshot["locators"])
        assert all(item.status == "completed" and item.executed_click
                   for item in operations if item.action_kind == "click")
        with factory() as db:
            retained = db.scalars(select(VisualLocatorHandoffModel).where(
                VisualLocatorHandoffModel.session_id == scope.session_id,
            )).one()
            click_ids = {str(item.id) for item in operations if item.action_kind == "click"}
            branches = [branch for branch in retained.payload["branches"] if any(
                step["operation_id"] in click_ids for step in branch["steps"]
            )]
            assert branches and all(branch["status"] == "blocked"
                                    and branch["reason_code"] == "ephemeral_locator"
                                    for branch in branches)
    elif variant == "button_tabs":
        assert names == {"Alpha", "Beta", "Lower Alpha", "Lower Beta"}
        assert calls == [["Alpha", "Beta"], ["Lower Alpha"], ["Lower Beta"]]
        clicked = [item for item in snapshot["locators"] if item.descriptor]
        ordered = sorted(clicked, key=lambda item: next(
            op.sequence for op in operations if op.id == item.operation_id
        ))
        assert [item.descriptor.value for item in ordered] == [
            "Alpha", "Lower Alpha", "Beta", "Lower Beta",
        ]
        assert not any(op.action_kind == "click" and op.purpose == "replay" for op in operations)
    elif variant == "visual_question":
        assert calls == [["Lower button"]]
        assert len(snapshot["locators"]) == 1
        assert all(page.interaction_scope == "visual_buttons" for page in snapshot["pages"])
        clicks = [op for op in operations if op.action_kind == "click"]
        assert len(clicks) == 1 and clicks[0].status == "completed" and clicks[0].executed_click
        assert all(control.role == "button" for page in snapshot["pages"]
                   for control in page.controls)
    elif variant == "buttons":
        assert names == {"Lower button"}
        assert calls == [["Lower button"]]
        assert all(page.interaction_scope == "buttons" for page in snapshot["pages"])
        assert all(control.role == "button" for page in snapshot["pages"]
                   for control in page.controls)
        assert sum(o.action_kind == "scroll" for o in operations) == 1
        assert not any(o.action_kind in {"back", "navigate"} and o.purpose != "setup"
                       for o in operations)
    elif variant == "popup_refresh":
        assert {"Popup", "Sibling", "Child content"} <= names
        root_page = operations[0].after_page_id
        sibling_locator = next(item for item in snapshot["locators"]
                               if item.descriptor.value == "Sibling")
        sibling = next(o for o in operations if o.id == sibling_locator.operation_id)
        assert sibling.before_page_id == root_page
        assert any(o.action_kind == "close_popup" and o.after_page_id == root_page
                   and o.sequence < sibling.sequence for o in operations)
        assert any(o.purpose == "setup" and o.action_kind == "wait" for o in operations)
    elif variant == "scroll":
        assert {"Header", "Lower content"} <= names
        assert any(o.action_kind == "scroll" and o.status == "completed" for o in operations)
        assert calls == [["Header"], ["Lower content"]]
    else:
        assert calls == [["Header"]]
        # The model-call budget does not prohibit deterministic observation.
        # Discover the lower target, but do not click it without another proposal.
        assert any(o.action_kind == "scroll" and o.status == "completed" for o in operations)
        assert names == {"Header"}
        with factory() as db:
            retained = db.scalars(select(VisualLocatorHandoffModel).where(
                VisualLocatorHandoffModel.session_id == scope.session_id,
            )).one()
            assert retained.generation_request_id is None


@pytest.mark.parametrize("variant", [
    "stable", "form_drift", "state_limit", "history_delay", "history_stuck",
    "history_duplicate", "history_duplicate_form", "history_overwritten",
    "history_scroll_reset", "history_scroll_reset_form", "history_scroll_reset_up",
    "mutation_cross_viewport",
])
def test_popup_restore_uses_returned_page_scroll_and_never_replays_effects(
    codex_database, live_browser_worker, monkeypatch, variant,
):
    target = live_browser_worker["target"] + (
        "/coverage-mutation-cross-viewport" if variant == "mutation_cross_viewport" else
        "/coverage-history-scroll-reset-form" if variant == "history_scroll_reset_form" else
        "/coverage-history-scroll-reset-up" if variant == "history_scroll_reset_up" else
        "/coverage-history-scroll-reset" if variant == "history_scroll_reset" else
        "/coverage-history-duplicate" if variant == "history_duplicate" else
        "/coverage-history-duplicate-form" if variant == "history_duplicate_form" else
        "/coverage-history-overwritten" if variant == "history_overwritten" else
        "/coverage-history-delay" if variant.startswith("history_") else
        "/coverage-popup-scroll-form" if variant == "form_drift" else "/coverage-popup-scroll"
    )
    policy = codex_policy(max_requests_per_minute=10_000, max_steps=5)
    factory, scope, uow, _, _ = database_tests.seed(codex_database, target=target, policy=policy)
    with factory.begin() as db:
        row = db.get(VisualExplorationSessionModel, scope.session_id)
        row.max_states, row.max_hops, row.step_timeout_seconds = 30, 10, 60
        db.add(ProjectExecutionPolicyModel(
            project_id=scope.project_id, tenant_id=scope.tenant_id,
            allowed_origins=[live_browser_worker["target"]],
            vision_max_states=30, vision_max_hops=10,
        ))
        SqlAlchemyConfigurationRepository(db).set(
            scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY,
            {"vision": policy.model_dump(mode="json")},
        )
    monkeypatch.setattr("application.vision_trace_events.decrypt_visual_intent",
                        lambda *_: "Check all buttons")
    calls = []

    class Planner:
        async def propose(self, **kwargs):
            await kwargs["budget"].reserve(evidence_bytes=100)
            bound = kwargs["bound"]
            calls.append([element.name for element in bound.observation.elements])
            output = parse_codex_output(json.dumps({"outcome": "candidates", "candidates": [
                {"kind": "click", "element_id": element.element_id, "confidence": .9,
                 "expected_outcome": "Check synthetic button"}
                for element in bound.observation.elements
            ]}).encode())
            return validate_candidates(output, bound, stage="dom", max_candidates=10)

    class Worker(HttpVisualWorker):
        async def execute(self, request):
            result = await super().execute(request)
            if variant == "state_limit" and result.operation.action_kind == "close_popup":
                with factory.begin() as db:
                    db.get(ProjectExecutionPolicyModel, scope.project_id).vision_max_states = 1
            if variant == "history_delay" and result.operation.action_kind == "back":
                async with httpx.AsyncClient() as probe:
                    await probe.get(live_browser_worker["target"] + "/history-release")
                    for _ in range(100):
                        visits = (await probe.get(
                            live_browser_worker["worker"] + "/fixture-visits"
                        )).json()
                        if visits.get("/history-hydrated"):
                            break
                        await asyncio.sleep(.05)
                    else:
                        pytest.fail("history hydration did not complete")
            return result

    async def scenario():
        settings = Settings(_env_file=None, vision_worker_secret="integration-fixture-only")
        async with httpx.AsyncClient(timeout=20) as client:
            async def forbidden(**_):
                pytest.fail("No live model calls")
            processor = VisionTraceEventProcessor(
                uow, Worker(client, live_browser_worker["worker"], settings.vision_worker_secret),
                settings, forbidden, codex_candidates=lambda _: Planner(),
            )
            return await processor.execute(OutboxEvent(
                id=uuid4(), tenant_id=scope.tenant_id,
                event_type="agent.visual_exploration.requested.v1", schema_version="v1",
                correlation_id=uuid4(), causation_id=None, idempotency_key="popup-scroll",
                payload={"session_id": str(scope.session_id)},
            ))

    state = asyncio.run(scenario())
    snapshot = uow.read_snapshot(scope)
    operations = snapshot["operations"]
    record = uow.get_session(scope.tenant_id, scope.session_id)
    details = (record.safe_failure_reason, calls,
               [(op.sequence, op.action_kind, op.status, op.outcome_code) for op in operations])
    if variant.startswith("history_scroll_reset"):
        visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
        assert visits.get("/record-button/reveal") == 1
        assert visits.get("/record-button/next") == 1
        assert not any(op.purpose == "replay" for op in operations)
        backs = [op for op in operations if op.action_kind == "back"]
        assert len(backs) == 1 and backs[0].status == "completed", details
        scrolls = [op for op in operations if op.sequence > backs[0].sequence
                   and op.action_kind == "scroll" and op.purpose == "restore"]
        if variant != "history_scroll_reset_form":
            assert visits.get("/record-button/sibling") == 1, details
            assert scrolls and all(op.status == "completed" for op in scrolls), details
            assert record.safe_failure_reason in {None, "exploration_coverage_incomplete"}
            assert all(op.status == "completed" for op in operations), details
        else:
            assert not visits.get("/record-button/sibling"), details
            assert state == "unavailable" and record.safe_failure_reason == "unsafe_replay"
        return
    succeeds = variant in {"stable", "history_delay", "history_duplicate"}
    assert state == ("completed" if succeeds else "unavailable"), details
    visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
    clicked = {path.removeprefix("/record-button/"): count
               for path, count in visits.items() if path.startswith("/record-button/")}
    if variant == "mutation_cross_viewport":
        # The historical top viewport was superseded before its own downward
        # scan. Keep that conservative coverage conclusion; do not rewrite it
        # merely because all fresh-context physical interactions succeeded.
        assert record.safe_failure_reason == "exploration_coverage_incomplete"
        assert any(p.scrollable for p in snapshot["pages"])
        assert calls == [["Reveal"], ["Top", "Sibling"], ["Mutate"], ["Sibling"]], details
        assert clicked == {"reveal": 1, "top": 1, "mutate": 1, "sibling": 1}
        assert all(op.status == "completed" for op in operations)
        assert not any(op.action_kind == "back" or op.purpose == "replay" for op in operations)
        from infrastructure.persistence.repositories import SqlAlchemyVisionRepository
        with factory() as db:
            edges = SqlAlchemyVisionRepository(db).list_trajectory_edges(
                scope.tenant_id, scope.session_id,
            )
        superseded = [edge for edge in edges if edge.outcome_code == "stale_dom_context"]
        assert len(superseded) == 1 and superseded[0].status == "terminal"
        assert all(op.proposal_id != superseded[0].proposal_id for op in operations)
        return
    if variant.startswith("history_"):
        assert calls == [["Reveal"], ["Next", "Sibling"]], details
        assert clicked == ({"reveal": 1, "next": 1, "sibling": 1} if succeeds else
                           {"reveal": 1, "next": 1})
        assert not any(op.purpose == "replay" for op in operations)
        backs = [op for op in operations if op.action_kind == "back"]
        assert len(backs) == 1
        assert backs[0].status == ("rejected" if variant == "history_overwritten" else "completed")
        refreshes = [op for op in operations if op.sequence > backs[0].sequence
                     and op.action_kind == "wait" and op.purpose == "setup"]
        assert len(refreshes) == (0 if variant in {"history_duplicate", "history_overwritten"}
                                  else 1 if succeeds else 2)
        assert all(op.status == "completed" and op.actual_after_frame_id for op in refreshes)
        if not succeeds:
            assert record.safe_failure_reason == "unsafe_replay"
        return
    assert calls == [["Reveal"], ["Top", "Sibling"], ["Popup"]], details
    assert clicked == ({"reveal": 1, "top": 1, "popup": 1, "sibling": 1}
                       if variant == "stable" else {"reveal": 1, "top": 1, "popup": 1})
    assert not any(op.purpose == "replay" for op in operations)
    closed = next(op for op in operations if op.action_kind == "close_popup")
    if variant == "state_limit":
        assert record.safe_failure_reason == "exploration_coverage_incomplete"
        assert closed.sequence == max(op.sequence for op in operations)
        return
    moved = next(op for op in operations if op.sequence > closed.sequence
                 and op.action_kind == "scroll" and op.purpose == "restore")
    assert closed.status == moved.status == "completed"
    assert closed.after_page_id == moved.before_page_id == operations[0].after_page_id
    assert closed.actual_after_frame_id and moved.actual_after_frame_id
    if variant == "form_drift":
        assert record.safe_failure_reason == "unsafe_replay"
    else:
        sibling = max((op for op in operations if op.action_kind == "click"),
                      key=lambda op: op.sequence)
        assert sibling.sequence > moved.sequence
        assert sibling.before_page_id == closed.after_page_id
