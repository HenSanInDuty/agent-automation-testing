"""Synthetic model -> live trace API -> approval -> pinned browser -> fixture report."""

import asyncio
import json
from time import perf_counter
from uuid import UUID

import httpx
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import generation, vision
from application.reporting_events import ReportingEventProcessor
from application.runs import RecordDeterministicResult, RequestRunReport
from application.vision_trace_events import VisionTraceEventProcessor
from auto_at.contracts.execution import RunStatus
from config import Settings, get_settings
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import GeneratedTestDraftModel
from infrastructure.persistence.models import TestRunModel as RunModel
from infrastructure.persistence.repositories import (
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunReportRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.runners import HttpPlaywrightTransport
from main import app
from sqlalchemy import func, select
from test_vision_live_persistence import (
    live_browser_worker,  # noqa: F401 -- reuse the owned loopback worker fixture
)
from test_vision_live_persistence import (
    test_publisher_browser_bfs_commits_live_frames_and_verified_sibling_restore as observe,
)

from benchmark.vision import summarize_locator_trace

pytest_plugins = ["vision_trace_fixtures"]


def test_trace_approval_execution_report_share_exact_provenance(
    trace_database, live_browser_worker, monkeypatch, tmp_path  # noqa: F811
):
    factory, scope, uow, _, store = trace_database
    settings = Settings(_env_file=None, playwright_worker_url=live_browser_worker["worker"])
    principal = Principal("fixture-reviewer", {scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {})
    monkeypatch.setattr(generation, "create_session_factory", lambda _: factory)
    monkeypatch.setattr(vision, "create_session_factory", lambda _: factory)
    monkeypatch.setattr(vision, "RustFSArtifactStore", lambda _: store)
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        current_tenant: lambda: scope.tenant_id,
        current_principal: lambda: principal,
        get_settings: lambda: settings,
    })
    latencies = []
    base = f"/api/v1/vision/explorations/{scope.session_id}"
    try:
        with TestClient(app) as client:
            def live_read():
                start = perf_counter()
                response = client.get(base + "/trace")
                latencies.append(perf_counter() - start)
                assert response.status_code == 200
                items = response.json()["items"]
                assert len(items) == 2 and all(o["status"] == "completed" for o in items)
                assert all(o["before"]["id"] and o["after"]["id"] for o in items)
                assert client.get(base + "/result").json()["exploration_state"] == "running"

            observe(trace_database, live_browser_worker, monkeypatch, "branches", live_read)
            snapshot = uow.read_snapshot(scope)
            package = snapshot["handoffs"][0]
            with factory() as session:
                draft = session.scalar(select(GeneratedTestDraftModel))
                draft_id = draft.id
                assert draft.provenance["vision_source"]["session_id"] == str(scope.session_id)
                assert draft.provenance["vision_source"]["handoff_id"] == str(package.id)
                assert draft.provenance["vision_source"]["handoff_hash"] == package.content_hash
                event = SqlAlchemyOutboxEventRepository(session).get_by_idempotency_key(
                    scope.tenant_id, "trace-publisher-fixture"
                )
            worker_url = live_browser_worker["worker"]
            visits_before = httpx.get(worker_url + "/fixture-visits").json()

            async def forbidden_model(**_):
                raise AssertionError("completed redelivery cannot invoke a model")

            # A completed session must be returned before touching even a worker port.
            assert asyncio.run(
                VisionTraceEventProcessor(uow, object(), settings, forbidden_model).execute(event)
            ) == "already_processed"
            visits_after = httpx.get(worker_url + "/fixture-visits").json()
            assert visits_after == visits_before
            assert visits_after["/a"] == visits_after["/b"] == 1

            decision = client.post(
                f"/api/v1/test-generations/drafts/{draft_id}/decision",
                json={"approved": True, "reason": "Approve synthetic fixture branches."},
            )
            assert decision.status_code == 200, decision.text
            run_id = UUID(decision.json()["linked_run_id"])
            duplicate = client.post(
                f"/api/v1/test-generations/drafts/{draft_id}/decision",
                json={"approved": True, "reason": "Approve synthetic fixture branches."},
            )
            assert duplicate.status_code == 200 and duplicate.json()["linked_run_id"] == str(run_id)
            with factory() as session:
                assert session.scalar(select(func.count()).select_from(RunModel)) == 1
                run = SqlAlchemyRunRepository(session).get(scope.tenant_id, run_id)
                request = run.request
            result = HttpPlaywrightTransport(worker_url).execute(request)
            assert result.contract_version == "v1" and result.status is RunStatus.PASSED, result
            assert result.runner_metadata["playwright_version"] == "1.50.1"
            rerun_visits = httpx.get(worker_url + "/fixture-visits").json()
            assert rerun_visits["/a"] == rerun_visits["/b"] == 2
            with factory.begin() as session:
                runs = SqlAlchemyRunRepository(session)
                run = RecordDeterministicResult(runs).execute(scope.tenant_id, result)
                outbox = SqlAlchemyOutboxEventRepository(session)
                RequestRunReport(outbox, SqlAlchemyAuditEventRepository(session)).execute(run)

            class ReportingModel:
                calls = 0

                async def ainvoke(self, payload, **kwargs):
                    self.calls += 1
                    return {"choices": [{"message": {"content": json.dumps({
                        "deterministic_status": "passed", "headline": "Fixture branches passed.",
                        "what_ran": "Two approved observed branch tests.", "observations": [],
                        "failure": None, "unverified_or_skipped": [],
                        "limitations": ["Synthetic target; no business-success assertion."],
                    })}}]}

            class NoArtifactReader:
                def read_verified_bytes(self, *_):
                    raise AssertionError("report fixture uses recorded metadata only")

            model = ReportingModel()
            with factory.begin() as session:
                report_event = SqlAlchemyOutboxEventRepository(session).get_by_idempotency_key(
                    scope.tenant_id, f"run-report:{run_id}:v1"
                )
                reports = SqlAlchemyRunReportRepository(session)
                processor = ReportingEventProcessor(
                    SqlAlchemyRunRepository(session), SqlAlchemyConfigurationRepository(session),
                    SqlAlchemyArtifactRepository(session), reports, NoArtifactReader(), settings,
                    model_factory=lambda *_: model,
                )
                assert asyncio.run(processor.execute(report_event)).status == "completed"
                repeated = asyncio.run(processor.execute(report_event))
                assert repeated.detail == "existing report reused"
                report = reports.get_for_run(scope.tenant_id, run_id)
                assert report.deterministic_status == "passed"
            assert model.calls == 1
            final = client.get(base + "/result").json()
            links = final["links"]
            assert links["handoff"]["id"] == str(package.id)
            assert links["draft"]["id"] == str(draft_id)
            assert links["run"]["id"] == str(run_id) and links["run"]["state"] == "passed"
            assert links["report"]["state"] == "available"
            assert uow.read_snapshot(scope) == snapshot
            metrics = summarize_locator_trace(
                snapshot, expected_locator_values={"Branch A", "Branch B"},
                post_commit_read_seconds=latencies, deterministic_rerun_succeeded=True,
                duplicate_physical_actions=sum(visits_after.values()) - sum(visits_before.values()),
            )
            assert metrics["wrong_target_count"] == 0
            assert metrics["frame_completeness"] == {"numerator": 10, "denominator": 10}
            (tmp_path / "locator-pipeline-metrics.json").write_text(json.dumps(metrics, indent=2))
            print("locator fixture aggregate: " + json.dumps(metrics, sort_keys=True))
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
