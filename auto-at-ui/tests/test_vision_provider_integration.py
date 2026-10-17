"""Actual legacy/v4 browser and SQL paths, with provider HTTP confined to MockTransport."""

import asyncio
import json
from base64 import b64decode
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from agents.prompts.vision import VISION_PROMPT_VERSION
from agents.shared.gemini import GeminiVisionLanguageModel
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, VisionPolicy
from agents.vision.intent import encrypt_visual_intent
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import vision as routes
from application.vision_events import VisionEventProcessor
from application.vision_trace_events import VisionTraceEventProcessor
from config import Settings
from domain.authorization import Principal, Role
from domain.runs import OutboxEvent
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    GenerationRequestModel,
    ProjectExecutionPolicyModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyVisionRepository,
)
from infrastructure.persistence.vision_unit_of_work import SqlAlchemyVisionPolicyReader
from infrastructure.vision.model_batch import VisionModelBatch
from infrastructure.vision_worker import HttpVisualWorker
from main import app
from sqlalchemy import func, select
from test_vision_live_persistence import live_browser_worker  # noqa: F401

pytest_plugins = ["vision_trace_fixtures"]


@pytest.mark.parametrize("backend", ["legacy", "v4"])
@pytest.mark.parametrize("variant", [
    "success", "401", "402", "429", "timeout", "invalid", "coordinates", "missing_key",
    "switch_before", "switch_after", "model_after", "disable_after", "revoke_after", "origin_after",
])
def test_provider_browser_trace_and_safe_stop(
    trace_database, live_browser_worker, monkeypatch, backend, variant,  # noqa: F811
):
    factory, scope, uow, _, store = trace_database
    origin = live_browser_worker["target"]
    settings = Settings(
        _env_file=None, gemini_api_key=None if variant == "missing_key" else "synthetic-gemini",
        huggingface_api_key="synthetic-hf-must-not-be-used",
        vision_worker_secret="integration-fixture-only", vision_max_requests_per_minute=10_000,
        vision_intent_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        artifact_root=live_browser_worker["root"],
        playwright_worker_url=live_browser_worker["worker"],
    )
    policy = VisionPolicy(
        enabled=True, provider="gemini", model="gemini-3.8-flash",
        raw_screenshot_transfer_accepted=True, raw_screenshot_transfer_provider="gemini",
        max_steps=2, max_session_seconds=60, max_requests_per_minute=10_000,
    )
    with factory.begin() as session:
        record = session.get(VisualExplorationSessionModel, scope.session_id)
        record.state = "queued"
        record.trace_version = backend
        record.lease_owner = record.lease_expires_at = None
        record.fencing_token = 0
        record.target_url, record.provider, record.model = origin, policy.provider, policy.model
        record.prompt_version = VISION_PROMPT_VERSION
        record.max_screenshot_bytes = 1_000_000
        record.max_requests_per_minute = 10_000
        record.max_steps, record.max_hops, record.max_states = 2, 1, 3
        record.encrypted_task_intent = encrypt_visual_intent(
            "Explore synthetic non-button controls", settings.vision_intent_encryption_key,
        )
        record.intent_retention_until = datetime.now(UTC) + timedelta(days=1)
        session.add(ProjectExecutionPolicyModel(
            project_id=scope.project_id, tenant_id=scope.tenant_id, allowed_origins=[origin],
            vision_max_hops=1, vision_max_states=3,
        ))
        SqlAlchemyConfigurationRepository(session).set(
            scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY, {"vision": policy.model_dump()},
        )
        event = OutboxEvent(
            id=uuid4(), tenant_id=scope.tenant_id,
            event_type="agent.visual_exploration.requested.v1",
            schema_version="v1", correlation_id=record.correlation_id, causation_id=None,
            idempotency_key="provider-fixture", payload={"session_id": str(scope.session_id)},
        )

    def change_policy():
        with factory.begin() as session:
            configs = SqlAlchemyConfigurationRepository(session)
            value = policy.model_dump()
            if variant.startswith("switch"):
                value.update(provider="huggingface", model="fixture-hf",
                             raw_screenshot_transfer_provider="huggingface")
            elif variant == "model_after":
                value["model"] = "unapproved-model"
            elif variant == "disable_after":
                value["enabled"] = False
            elif variant == "revoke_after":
                value.update(enabled=False, raw_screenshot_transfer_accepted=False,
                             raw_screenshot_transfer_provider=None)
            elif variant == "origin_after":
                session.get(ProjectExecutionPolicyModel, scope.project_id).allowed_origins = []
            configs.set(scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY, {"vision": value})

    requests = []

    async def provider(request):
        requests.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["authorization"] == "Bearer synthetic-gemini"
        payload = json.loads(request.content)
        assert payload["model"] == "gemini-3.8-flash"
        uri = payload["messages"][1]["content"][1]["image_url"]["url"]
        assert b64decode(uri.partition(",")[2]).startswith(b"\x89PNG")
        if backend == "v4":
            # An independent reader sees committed navigation during the provider call.
            snapshot = uow.read_snapshot(scope)
            assert len(snapshot["operations"]) == 1 and len(snapshot["frames"]) == 2
            assert snapshot["operations"][0].status == "completed"
        if variant.endswith("_after"):
            change_policy()
        if variant in {"401", "402", "429"}:
            return httpx.Response(int(variant), text="private-provider-error-sentinel")
        if variant == "timeout":
            raise httpx.ReadTimeout("private-provider-error-sentinel")
        content = "not json" if variant == "invalid" else json.dumps({"candidates": [
            {"kind": "click", "x": 2 if variant == "coordinates" else 100 / 1279,
             "y": 40 / 719, "confidence": 0.9, "expected_outcome": "Open Branch A"},
        ]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    def model_factory(settings, policy, **kwargs):
        return GeminiVisionLanguageModel(
            api_key=settings.gemini_api_key, model=policy.model,
            transport=httpx.MockTransport(provider), **kwargs,
        )

    def no_drive(**_):
        pytest.fail("Gemini must not construct a Drive store")

    shared = VisionModelBatch(settings, model_factory=model_factory, image_store_factory=no_drive)

    async def batch(**kwargs):
        if variant == "switch_before":
            change_policy()
        return await shared(**kwargs)

    async def scenario():
        if backend == "v4":
            async with httpx.AsyncClient(timeout=10) as client:
                processor = VisionTraceEventProcessor(
                    uow, HttpVisualWorker(client, settings.playwright_worker_url,
                                          settings.vision_worker_secret), settings, batch,
                )
                result = await processor.execute(event)
                assert await processor.execute(event) == "already_processed"
                return result
        with factory.begin() as session:
            def write_frame(record, content):
                store.frames[record.storage_key] = content
            store.write_replay_frame = write_frame
            processor = VisionEventProcessor(
                SqlAlchemyVisionRepository(session), SqlAlchemyConfigurationRepository(session),
                SqlAlchemyGenerationRepository(session), SqlAlchemyAuditEventRepository(session),
                SqlAlchemyActivityEventRepository(session),
                SqlAlchemyOutboxEventRepository(session), settings, store,
                model_batch=batch, read_policy=SqlAlchemyVisionPolicyReader(factory),
            )
            result = await processor.execute(event)
            assert await processor.execute(event) == "already_processed"
            return result

    reason = {
        "401": "provider_auth_failed", "402": "provider_billing_required",
        "429": "provider_rate_limited", "timeout": "provider_timeout",
        "invalid": "model_output_invalid", "coordinates": "model_output_invalid",
        "missing_key": "provider_not_configured",
    }.get(variant, "policy_disabled" if variant != "success" else None)
    assert asyncio.run(scenario()) == ("unavailable" if reason else "completed")
    assert len(requests) == (0 if variant in {"missing_key", "switch_before"} else 1)
    record = uow.get_session(scope.tenant_id, scope.session_id)
    assert record.safe_failure_reason == reason
    assert (record.provider, record.model) == ("gemini", "gemini-3.8-flash")
    with factory() as session:
        repository = SqlAlchemyVisionRepository(session)
        states = repository.list_states(scope.tenant_id, scope.session_id)
        proposals = repository.list_actions(scope.tenant_id, scope.session_id)
        assert len(states) == (1 if reason else 2)
        assert len(proposals) == (0 if reason else 1)
        if reason:
            assert session.scalar(select(func.count()).select_from(GenerationRequestModel)) == 0
        if backend == "legacy":
            frames = repository.list_replay_frames(scope.tenant_id, scope.session_id)
            assert len(frames) == len(states)
            assert all(store.frames[f.storage_key].startswith(b"\x89PNG") for f in frames)
        else:
            snapshot = uow.read_snapshot(scope)
            assert len(snapshot["frames"]) == (2 if reason else 4)
            if not reason:
                click = snapshot["operations"][1]
                assert click.action_kind == "click" and click.proposal_id == proposals[0].id
                assert snapshot["locators"][0].descriptor.value == "Branch A"
                assert snapshot["locators"][0].descriptor.strategy == "role"
                assert snapshot["locators"][0].descriptor.role == "link"

    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        current_tenant: lambda: scope.tenant_id,
        current_principal: lambda: Principal(
            "reader", {scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {},
        ),
    })
    monkeypatch.setattr(routes, "create_session_factory", lambda _: factory)
    monkeypatch.setattr(routes, "RustFSArtifactStore", lambda _: store)
    try:
        with TestClient(app) as client:
            base = f"/api/v1/vision/explorations/{scope.session_id}"
            result = client.get(base + "/result")
            assert result.status_code == 200
            assert result.json()["completion_reason"] == (reason or "exploration_finished")
            progress = client.get(base + "/activities")
            assert "private-provider-error-sentinel" not in result.text + progress.text
            if reason:
                assert any(e["metadata"].get("reason_code") == reason for e in progress.json())
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
