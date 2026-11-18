"""Credential-free generation transport and approval-boundary regression checks."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agents.generation.planner import build_planning_prompt
from agents.generation.vision_plan import plan_vision_test
from agents.prompts.codex_generation import build_prompt
from application.codex_generation_bridge import GenerationBridgeService
from application.generation_events import GenerationEventProcessor
from auto_at.contracts.codex_bridge import CodexBridgeReadiness, CodexUsage, content_hash
from auto_at.contracts.codex_generation import CodexGenerationJob, GenerationProviderPolicy
from auto_at.contracts.generation import (
    GeneratedTestPlannerOutput,
    VisionGroundedPlannerOutput,
    VisionPlanningSource,
    request_hash,
)
from auto_at.contracts.generation import (
    TestGenerationPlanningRequest as PlanningRequest,
)
from config import Settings
from domain.activity import ActivityEvent
from domain.codex_bridge import BridgeProcessResult
from infrastructure.codex_bridge.generation_model import CodexGenerationModel, GenerationBridgeError
from infrastructure.codex_bridge.generation_spool import GenerationSpool
from test_generation_event_processor import Audits, Model, Repository, event, request
from test_vision_handoff import branch_fixture

SOURCE = "import { test, expect } from '@playwright/test';\n" \
         "test('home', async ({ page }) => { await page.goto('https://example.test'); });"


def policy(**changes):
    return GenerationProviderPolicy(provider="codex_cli", model="gpt-6-luna",
                                    **{"text_transfer_accepted": True, **changes})


class Ready:
    def read(self, *_):
        return CodexBridgeReadiness(configured=True, online=True, authenticated=True,
                                   capabilities_qualified=True)


class Process:
    def __init__(self):
        self.calls = 0
        self.payload = None

    async def run(self, req, directory, data, stop):
        self.calls += 1
        self.payload = json.loads(data)
        assert stop() is None
        return BridgeProcessResult(output=GeneratedTestPlannerOutput(
            title="Synthetic draft", playwright_test_source=SOURCE,
            assumptions=[], stop_conditions=[],
        ), usage=CodexUsage(input_tokens=30, output_tokens=10))


@pytest.fixture
def bridge(tmp_path):
    item = request()
    settings = Settings(_env_file=None, codex_bridge_enabled=True, codex_bridge_id=uuid4(),
                        codex_bridge_allowed_tenant=item.tenant_id,
                        codex_bridge_host_spool=str(tmp_path),
                        codex_bridge_executable="/usr/local/bin/codex")
    spool = GenerationSpool(tmp_path / "generation", settings.codex_bridge_id, item.tenant_id)
    process = Process()
    reservations = []
    selected = policy()
    model = CodexGenerationModel(settings=settings, request=item, policy=selected,
                                read_policy=lambda: selected, spool=spool, readiness=Ready(),
                                reserve_call=reservations.append, poll_seconds=0.001)
    return SimpleNamespace(item=item, spool=spool, process=process, model=model,
                           service=GenerationBridgeService(spool, process),
                           reservations=reservations)


def payload(item):
    planning = PlanningRequest(id=item.id, project_id=item.project_id,
                               correlation_id=item.correlation_id,
                               target_url="https://example.test/?token=secret#private",
                               redacted_request="Check home",
                               request_hash=request_hash("Check home"))
    return build_planning_prompt(planning, ["https://example.test"])


@pytest.mark.asyncio
async def test_text_job_completes_once_without_images_and_redacts_url(bridge):
    events = []
    bridge.model.on_event = lambda stage, metadata: events.append(ActivityEvent.create(
        tenant_id=bridge.item.tenant_id, correlation_id=bridge.item.correlation_id,
        source="generation", stage=stage, status="running", safe_summary="Synthetic generation.",
        occurred_at=datetime.now(UTC), metadata=metadata,
    ))
    task = asyncio.create_task(bridge.model.ainvoke(payload(bridge.item)))
    for _ in range(200):
        await asyncio.sleep(0.001)
        await bridge.service.run_once()
        if task.done():
            break
    result = await asyncio.wait_for(task, timeout=2)
    assert json.loads(result["choices"][0]["message"]["content"])["title"] == "Synthetic draft"
    assert bridge.process.calls == len(bridge.reservations) == 1
    assert events[-1].metadata["usage"]["input_count"] == 30
    assert bridge.process.payload["target_url"] == "https://example.test/"
    assert not bridge.spool.has_file(bridge.reservations[0], "generation.json")
    assert not bridge.spool.has_file(bridge.reservations[0], "screenshot.png")
    await bridge.service.run_once()
    assert bridge.process.calls == 1
    with pytest.raises(GenerationBridgeError, match="interrupted"):
        await bridge.model.ainvoke(payload(bridge.item))


@pytest.mark.asyncio
async def test_policy_switch_cancels_without_provider_fallback(bridge):
    task = asyncio.create_task(bridge.model.ainvoke(payload(bridge.item)))
    await asyncio.sleep(0.01)
    bridge.model.read_policy = lambda: policy(text_transfer_accepted=False)
    with pytest.raises(GenerationBridgeError, match="policy_revoked"):
        await task
    await bridge.service.run_once()
    assert bridge.process.calls == 0


def published(bridge):
    data = b'{"redacted_request":"synthetic"}'
    now = datetime.now(UTC)
    job = CodexGenerationJob(job_id=bridge.item.id, bridge_id=bridge.model.settings.codex_bridge_id,
                             tenant_id=bridge.item.tenant_id, project_id=bridge.item.project_id,
                             correlation_id=bridge.item.correlation_id, kind="text",
                             policy_hash=content_hash(policy()),
                             input_hash=hashlib.sha256(data).hexdigest(), input_bytes=len(data),
                             created_at=now, deadline=now + timedelta(seconds=120))
    bridge.spool.publish(job, data)
    bridge.spool.authorize(job, now + timedelta(seconds=8))
    return job


@pytest.mark.asyncio
async def test_restart_after_claim_never_relaunches(bridge):
    job = published(bridge)
    bridge.spool.claim(job)
    await bridge.service.run_once()
    assert bridge.spool.result(job).failure_code == "bridge_interrupted"
    assert bridge.process.calls == 0


def test_hash_scope_and_expiry_are_checked(bridge):
    job = published(bridge)
    with pytest.raises(ValueError):
        bridge.spool.payload(job.model_copy(update={"tenant_id": "foreign"}))
    (bridge.spool.path(job.job_id) / "generation.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="input mismatch"):
        bridge.spool.payload(job)
    assert bridge.spool.stop_reason(job, job.deadline) == "bridge_deadline_exceeded"


@pytest.mark.asyncio
async def test_transfer_consent_required_before_publication(bridge):
    bridge.model.policy = policy(text_transfer_accepted=False)
    with pytest.raises(GenerationBridgeError, match="policy_revoked"):
        await bridge.model.ainvoke(payload(bridge.item))
    assert bridge.reservations == []
    assert bridge.spool.jobs() == []


def test_centralized_generation_prompt_keeps_vision_selection_only():
    prompt = json.loads(build_prompt("vision", '{"redacted_request":"synthetic"}'))
    assert "never select blocked" in prompt["planning_instructions"].lower()
    assert prompt["context"] == {"redacted_request": "synthetic"}


@pytest.mark.asyncio
async def test_vision_evidence_round_trip_selects_recorded_branches_only(bridge):
    scope, _, handoff = branch_fixture()
    planning = PlanningRequest(
        id=bridge.item.id, project_id=scope.project_id, correlation_id=bridge.item.correlation_id,
        target_url="https://fixture.test/", redacted_request="Check recorded branches",
        request_hash=request_hash("Check recorded branches"),
        vision_source=VisionPlanningSource(session_id=scope.session_id, handoff_id=handoff.id,
                                          handoff_hash=handoff.content_hash),
    )
    async def run(job, directory, data, stop):
        assert job.kind == "vision" and stop() is None
        context = json.loads(data)
        assert "output_schema" in context and "screenshot" not in context
        return BridgeProcessResult(output=VisionGroundedPlannerOutput(
            title="Recorded branches", selected_branch_ids=[b.id for b in handoff.branches],
        ))
    bridge.process.run = run
    task = asyncio.create_task(plan_vision_test(bridge.model, planning, handoff, 1000, 100_000))
    for _ in range(200):
        await asyncio.sleep(0.001)
        await bridge.service.run_once()
        if task.done():
            break
    output = await asyncio.wait_for(task, 2)
    assert output.selected_branch_ids == [b.id for b in handoff.branches]
    assert not hasattr(output, "playwright_test_source")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["codex_cli", "huggingface"])
async def test_selected_provider_produces_pending_draft(monkeypatch, provider):
    item = request()
    repository = Repository(item, SimpleNamespace(allowed_origins=["https://example.test"]))
    selected = (policy() if provider == "codex_cli" else GenerationProviderPolicy(
        provider="huggingface", model="fixture/hf", text_transfer_accepted=True,
    ))
    configs = SimpleNamespace(get=lambda *_: {"generation": selected.model_dump()})
    calls = []
    def hf(_settings, runtime):
        calls.append(runtime.provider)
        return Model(SOURCE)
    def codex(*_):
        calls.append("codex_cli")
        return Model(SOURCE)
    monkeypatch.setattr("application.generation_events.create_language_model", hf)
    processor = GenerationEventProcessor(repository, configs, Audits(), Settings(_env_file=None),
                                         codex_model_factory=codex)
    assert await processor.execute(event(item)) == "completed"
    assert calls == [provider]
    assert repository.draft.state == "pending_review"
    assert repository.draft.provenance["provider"] == provider
    assert repository.draft.linked_run_id is None
