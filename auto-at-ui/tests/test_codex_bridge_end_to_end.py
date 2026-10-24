"""Fake Codex -> real browser -> pending draft -> human approval -> deterministic run."""

import asyncio
import json
from time import perf_counter
from uuid import UUID

import pytest
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import generation
from application.generation_events import GenerationEventProcessor
from application.runs import RecordDeterministicResult
from auto_at.contracts.execution import RunStatus
from config import get_settings
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import CodexBridgeJobModel
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.runners import HttpPlaywrightTransport
from main import app
from sqlalchemy import select
from test_codex_bridge_repository import codex_database  # noqa: F401
from test_codex_exploration_integration import (
    test_codex_browser_jobs_bindings_and_safe_stops as explore,
)
from test_vision_live_persistence import live_browser_worker  # noqa: F401

pytest_plugins = ["vision_trace_fixtures"]


@pytest.mark.parametrize("mode", ["dom", "image"])
def test_codex_draft_requires_approval_and_preserves_execution_v1(
    codex_database, live_browser_worker, tmp_path, monkeypatch, mode,  # noqa: F811
):
    captured = []
    began = perf_counter()
    explore(
        codex_database, live_browser_worker, tmp_path, monkeypatch, mode,
        on_complete=lambda *values: captured.append(values),
        allow_generation=True,
    )
    exploration_seconds = perf_counter() - began
    factory, scope, uow, _, settings, process = captured[0]
    settings = settings.model_copy(update={
        "playwright_worker_url": live_browser_worker["worker"],
        "artifact_root": live_browser_worker["root"],
    })
    package = uow.read_snapshot(scope)["handoffs"][0]

    class SelectionModel:
        async def ainvoke(self, payload, **kwargs):
            context = json.loads(payload["messages"][1]["content"])
            return {"choices": [{"message": {"content": json.dumps({
                "title": "Synthetic Codex branches",
                "selected_branch_ids": [b["id"] for b in context["branches"]],
                "assertions": context["allowed_assertions"],
            })}}]}

    monkeypatch.setattr(
        "application.generation_events.create_language_model", lambda *_: SelectionModel()
    )
    with factory.begin() as db:
        events = SqlAlchemyOutboxEventRepository(db).list_unpublished(100)
        event = next(e for e in events if e.event_type == "agent.test_generation.requested.v1")
        repository = SqlAlchemyGenerationRepository(db)
        processor = GenerationEventProcessor(
            repository, SqlAlchemyConfigurationRepository(db),
            SqlAlchemyAuditEventRepository(db), settings,
        )
        assert asyncio.run(processor.execute(event)) == "completed"
        draft = repository.get_draft_for_request(scope.tenant_id, UUID(event.payload["request_id"]))
        assert draft.state == "pending_review" and draft.linked_run_id is None
        assert draft.provenance["vision_source"]["handoff_hash"] == package.content_hash
        draft_id = draft.id

    principal = Principal("human-fixture", {scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {})
    monkeypatch.setattr(generation, "create_session_factory", lambda _: factory)
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        current_tenant: lambda: scope.tenant_id, current_principal: lambda: principal,
        get_settings: lambda: settings,
    })
    try:
        with TestClient(app) as client:
            url = f"/api/v1/test-generations/drafts/{draft_id}/decision"
            response = client.post(url, json={"approved": True, "reason": "Synthetic review"})
            assert response.status_code == 200, response.text
            run_id = UUID(response.json()["linked_run_id"])
            duplicate = client.post(url, json={"approved": True, "reason": "Synthetic review"})
            assert duplicate.json()["linked_run_id"] == str(run_id)
        with factory() as db:
            run = SqlAlchemyRunRepository(db).get(scope.tenant_id, run_id)
            request = run.request
        result = HttpPlaywrightTransport(live_browser_worker["worker"]).execute(request)
        assert result.contract_version == request.contract_version == "v1"
        assert result.status == RunStatus.PASSED, result
        assert result.runner_metadata["playwright_version"] == "1.50.1"
        with factory.begin() as db:
            persisted = RecordDeterministicResult(SqlAlchemyRunRepository(db)).execute(
                scope.tenant_id, result
            )
            assert persisted.status.value == "passed"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)

    with factory() as db:
        jobs = db.scalars(select(CodexBridgeJobModel)).all()
        metrics = {
            "mode": mode, "responses": "fake_cli", "cli_calls": len(process.calls),
            "image_calls": sum(r.stage == "image" for r in process.calls),
            "verified_actions": len(uow.read_snapshot(scope)["locators"]),
            "unique_branch_actions": 2, "deterministic_rerun": "passed",
            "exploration_seconds": round(exploration_seconds, 3),
            "input_tokens_synthetic": sum((j.usage or {}).get("input_tokens", 0) for j in jobs),
            "output_tokens_synthetic": sum((j.usage or {}).get("output_tokens", 0) for j in jobs),
        }
    assert metrics["cli_calls"] == (2 if mode == "image" else 1)
    assert metrics["verified_actions"] == 2
    (tmp_path / "codex-metrics.json").write_text(json.dumps(metrics, indent=2))
    print("codex fixture aggregate: " + json.dumps(metrics, sort_keys=True))
