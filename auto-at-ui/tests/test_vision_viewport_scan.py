"""A stale model scroll is discarded; fresh browser context owns viewport discovery."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import test_codex_bridge_repository as database_tests
import test_vision_live_persistence as browser_tests
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY
from application.codex_candidates import CodexCandidateService
from application.vision_trace_events import VisionTraceEventProcessor
from auto_at.contracts.codex_bridge import parse_codex_output
from config import Settings
from domain.runs import OutboxEvent
from infrastructure.persistence.models import (
    ProjectExecutionPolicyModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.repositories import SqlAlchemyConfigurationRepository
from infrastructure.vision_worker import HttpVisualWorker
from test_codex_candidate_service import codex_policy

pytest_plugins = ["vision_trace_fixtures"]
codex_database = database_tests.codex_database
live_browser_worker = browser_tests.live_browser_worker


@pytest.mark.parametrize("variant", [
    "abstain", "legacy_scroll", "call_limit", "context_rejected", "capture_unstable",
    "prepare_once", "prepare_always",
])
def test_deterministic_scan_crosses_carousel_without_executing_model_delta(
    codex_database, live_browser_worker, monkeypatch, variant,
):
    target = live_browser_worker["target"] + "/scan-carousel"
    policy = codex_policy(max_steps=1 if variant == "call_limit" else 5,
                          max_requests_per_minute=10_000)
    factory, scope, uow, _, _ = database_tests.seed(
        codex_database, target=target, policy=policy,
    )
    with factory.begin() as db:
        row = db.get(VisualExplorationSessionModel, scope.session_id)
        row.max_states, row.max_hops, row.step_timeout_seconds = 30, 8, 60
        db.add(ProjectExecutionPolicyModel(
            project_id=scope.project_id, tenant_id=scope.tenant_id,
            allowed_origins=[live_browser_worker["target"]], vision_max_hops=8,
            vision_max_states=30,
        ))
        SqlAlchemyConfigurationRepository(db).set(scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY,
                                                  {"vision": policy.model_dump(mode="json")})
    monkeypatch.setattr("application.vision_trace_events.decrypt_visual_intent",
                        lambda *_: "Explore the lower action")
    calls, deltas, context_checks = [], [], []

    async def exchange(**kwargs):
        elements = kwargs["bound"].observation.elements
        calls.append([e.name for e in elements])
        lower = next((e for e in elements if e.name == "Lower action"), None)
        if lower:
            value = {"outcome": "candidates", "candidates": [{"kind": "click",
                     "element_id": lower.element_id, "confidence": .9,
                     "expected_outcome": "Open lower synthetic action"}]}
        else:
            # Emulate provider latency spanning the autoplay tick, without a provider.
            await asyncio.sleep(3.1)
            value = ({"outcome": "candidates", "candidates": [{"kind": "scroll",
                      "delta_y": -1700, "confidence": .9, "expected_outcome": "Scroll"}]}
                     if variant == "legacy_scroll" else
                     {"outcome": "stop", "reason": "no_safe_action"})
        return SimpleNamespace(output=parse_codex_output(json.dumps(value).encode()),
                               failure_code=None)

    class Worker(HttpVisualWorker):
        async def prepare(self, request):
            if request.action.kind == "scroll":
                deltas.append(request.action.delta_y)
                assert request.proposal_id is None
                if variant == "prepare_always" or (variant == "prepare_once" and len(deltas) == 1):
                    await asyncio.sleep(3.1)
            return await super().prepare(request)

        async def observe_dom(self, request):
            if request.revalidate_context_only:
                context_checks.append(request)
                if variant in {"context_rejected", "capture_unstable"}:
                    from domain.vision import VisionObservationUnavailable
                    raise VisionObservationUnavailable(
                        "stale_dom_context" if variant == "context_rejected"
                        else "state_changed_during_observation"
                    )
            return await super().observe_dom(request)

    async def forbidden(**_):
        pytest.fail("No provider fallback")

    async def scenario():
        settings = Settings(_env_file=None, vision_worker_secret="integration-fixture-only")
        async with httpx.AsyncClient(timeout=20) as client:
            processor = VisionTraceEventProcessor(
                uow, Worker(client, live_browser_worker["worker"], settings.vision_worker_secret),
                settings, forbidden, codex_candidates=lambda _: CodexCandidateService(exchange),
            )
            event = OutboxEvent(id=uuid4(), tenant_id=scope.tenant_id,
                               event_type="agent.visual_exploration.requested.v1",
                               schema_version="v1", correlation_id=uuid4(), causation_id=None,
                               idempotency_key="deterministic-scan",
                               payload={"session_id": str(scope.session_id)})
            await processor.execute(event)

    asyncio.run(scenario())
    record = uow.get_session(scope.tenant_id, scope.session_id)
    assert context_checks, (record.safe_failure_reason, calls,
                            [(op.sequence, op.status, op.outcome_code)
                             for op in uow.read_snapshot(scope)["operations"]])
    if variant == "context_rejected":
        assert record.safe_failure_reason == "stale_dom_context" and deltas == []
        assert len(context_checks) == 1
    elif variant == "capture_unstable":
        assert record.safe_failure_reason == "state_changed_during_observation" and deltas == []
        assert len(context_checks) == 3
    elif variant == "prepare_always":
        assert deltas == [576, 576, 576]
        assert record.safe_failure_reason in {"state_mismatch", "state_changed_during_prepare"}
    else:
        assert 1 <= len(deltas) <= 3 and set(deltas) == {576}, (record.safe_failure_reason, calls,
                                [(op.sequence, op.action_kind, op.status, op.outcome_code)
                                 for op in uow.read_snapshot(scope)["operations"]])
        assert sum(op.action_kind == "scroll" and op.status == "completed"
                   for op in uow.read_snapshot(scope)["operations"]) == 1
        assert record.safe_failure_reason in {
            "exploration_coverage_incomplete", "exploration_call_limit",
        }, record.safe_failure_reason
    visits = httpx.get(live_browser_worker["worker"] + "/fixture-visits").json()
    assert visits.get("/record-button/lower", 0) == (
        0 if variant in {"context_rejected", "capture_unstable", "call_limit", "prepare_always"}
        else 1
    )
    assert len(calls) <= policy.max_steps
    assert not any(op.status == "unknown" for op in uow.read_snapshot(scope)["operations"])
