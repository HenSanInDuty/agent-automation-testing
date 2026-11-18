"""Changed copies require a fresh model decision before any physical action."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
import test_codex_bridge_repository as database_tests
import test_vision_live_persistence as browser_tests
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY
from agents.vision.codex_service import validate_candidates
from application.vision_trace_events import VisionTraceEventProcessor
from auto_at.contracts.codex_bridge import parse_codex_output
from config import Settings
from domain.runs import OutboxEvent
from infrastructure.persistence.models import (
    ProjectExecutionPolicyModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.repositories import (
    SqlAlchemyConfigurationRepository,
    SqlAlchemyVisionRepository,
)
from infrastructure.vision_worker import HttpVisualWorker
from test_codex_candidate_service import codex_policy

pytest_plugins = ["vision_trace_fixtures"]
codex_database = database_tests.codex_database
live_browser_worker = browser_tests.live_browser_worker


@pytest.mark.parametrize("mutation", ["swap", "replacement", "form", "limit"])
def test_changed_video_copy_retires_proposal_and_requires_new_approval(
    codex_database, live_browser_worker, monkeypatch, mutation,
):
    policy = codex_policy(max_requests_per_minute=10000, max_steps=1 if mutation == "limit" else 5)
    factory, scope, uow, _, _ = database_tests.seed(codex_database,
        target=live_browser_worker["target"] + "/coverage-video-preflight", policy=policy)
    with factory.begin() as db:
        row = db.get(VisualExplorationSessionModel, scope.session_id)
        row.max_states, row.max_hops, row.step_timeout_seconds = 30, 10, 60
        db.add(ProjectExecutionPolicyModel(project_id=scope.project_id, tenant_id=scope.tenant_id,
            allowed_origins=[live_browser_worker["target"]],
            vision_max_hops=10, vision_max_states=30))
        SqlAlchemyConfigurationRepository(db).set(scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY,
                                                  {"vision": policy.model_dump(mode="json")})
    monkeypatch.setattr("application.vision_trace_events.decrypt_visual_intent",
                        lambda *_: "Check all buttons")
    calls = []

    class Planner:
        async def propose(self, **kwargs):
            await kwargs["budget"].reserve(evidence_bytes=100)
            bound = kwargs["bound"]
            calls.append([e.element_id for e in bound.observation.elements])
            output = parse_codex_output(json.dumps({"outcome": "candidates", "candidates": [
                {"kind": "click", "element_id": e.element_id, "confidence": .9,
                 "expected_outcome": "Open approved synthetic video"}
                for e in bound.observation.elements
            ]}).encode())
            result = validate_candidates(output, bound, stage="dom", max_candidates=10)
            if len(calls) == 1:
                async with httpx.AsyncClient() as probe:
                    response = await probe.get(live_browser_worker["worker"]
                                               + "/fixture-preflight-mutate/" + mutation)
                    response.raise_for_status()
            return result

    async def scenario():
        settings = Settings(_env_file=None, vision_worker_secret="integration-fixture-only")
        async with httpx.AsyncClient(timeout=20) as client:
            async def forbidden(**_):
                pytest.fail("No live model calls")
            processor = VisionTraceEventProcessor(uow,
                HttpVisualWorker(client, live_browser_worker["worker"],
                                 settings.vision_worker_secret),
                settings, forbidden, codex_candidates=lambda _: Planner())
            return await processor.execute(OutboxEvent(id=uuid4(), tenant_id=scope.tenant_id,
                event_type="agent.visual_exploration.requested.v1", schema_version="v1",
                correlation_id=uuid4(), causation_id=None, idempotency_key="target-preflight",
                payload={"session_id": str(scope.session_id)}))

    state = asyncio.run(scenario())
    snapshot = uow.read_snapshot(scope)
    ops = snapshot["operations"]
    clicks = [o for o in ops if o.purpose == "explore" and o.action_kind == "click"]
    with factory() as db:
        edges = SqlAlchemyVisionRepository(db).list_trajectory_edges(
            scope.tenant_id, scope.session_id,
        )
    stale = [e for e in edges if e.outcome_code == "stale_dom_context"]
    detail = (uow.get_session(scope.tenant_id, scope.session_id).safe_failure_reason,
              [(o.sequence, o.action_kind, o.status, o.outcome_code) for o in ops])
    assert stale, detail
    assert not any(o.proposal_id in {e.proposal_id for e in stale} for o in clicks), detail
    if mutation in {"form", "limit"}:
        assert not clicks, detail
        assert len(calls) == 1
        assert state == "unavailable"
    else:
        assert state == "completed", detail
        assert len(calls) == 2
        assert not set(calls[0]) & set(calls[1])
        assert len(clicks) == 2 and all(o.status == "completed" for o in clicks), detail
