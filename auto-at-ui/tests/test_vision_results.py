from datetime import UTC, datetime
from uuid import uuid4

import pytest
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import vision as routes
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from main import app
from vision_trace_fixtures import complete_operation, operation

pytest_plugins = ["vision_trace_fixtures"]


@pytest.fixture
def result_client(trace_database, monkeypatch):
    factory, scope, uow, lease, store = trace_database
    root = complete_operation(uow, lease, operation(scope))
    principal = Principal("reader", {scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {})
    monkeypatch.setattr(routes, "create_session_factory", lambda _: factory)
    monkeypatch.setattr(routes, "RustFSArtifactStore", lambda _: store)
    app.dependency_overrides[current_tenant] = lambda: scope.tenant_id
    app.dependency_overrides[current_principal] = lambda: principal
    try:
        yield TestClient(app), f"/api/v1/vision/explorations/{scope.session_id}", root
    finally:
        app.dependency_overrides.pop(current_tenant, None)
        app.dependency_overrides.pop(current_principal, None)


def test_trace_pagination_detects_concurrent_append_and_excludes_private_keys(
    result_client, trace_database
):
    client, base, root = result_client
    _, scope, uow, lease, _ = trace_database
    first = client.get(base + "/trace?limit=1")
    assert first.status_code == 200
    data = first.json()
    assert first.headers["cache-control"] == "private, no-store"
    assert data["items"][0]["before"]["id"] == str(root.actual_before_frame_id)
    assert "storage_key" not in first.text and "encrypted" not in first.text
    second = complete_operation(
        uow, lease, operation(scope, sequence=2, parent_operation_id=root.id)
    )
    assert (
        client.get(base + f"/trace?after_sequence=1&revision={data['revision']}").status_code == 409
    )
    page = client.get(base + "/trace?after_sequence=1&limit=1").json()
    assert [item["id"] for item in page["items"]] == [str(second.id)]
    assert client.get(base + "/trace?limit=101").status_code == 422
    assert client.get(base + "/trace?after_sequence=-1").status_code == 422


@pytest.mark.parametrize("caller", ["service", "foreign_project", "foreign_tenant"])
def test_all_read_routes_hide_unauthorized_session(result_client, trace_database, caller):
    client, base, root = result_client
    _, scope, _, _, _ = trace_database
    principal = {
        "service": Principal(
            "worker", {scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {}, is_service=True
        ),
        "foreign_project": Principal(
            "reader", {}, {(scope.tenant_id, uuid4()): frozenset({Role.VIEWER})}
        ),
        "foreign_tenant": Principal("reader", {"elsewhere": frozenset({Role.TENANT_ADMIN})}, {}),
    }[caller]
    app.dependency_overrides[current_principal] = lambda: principal
    for suffix in (
        "/trace",
        "/result",
        "/result/export",
        "/locators",
        f"/operation-frames/{root.actual_before_frame_id}",
    ):
        assert client.get(base + suffix).status_code == 404


def test_frame_delete_keeps_tombstone_and_export_without_bytes(result_client, trace_database):
    client, base, root = result_client
    frame_path = base + f"/operation-frames/{root.actual_before_frame_id}"
    assert client.get(frame_path).status_code == 200
    assert client.request("DELETE", frame_path, json={"confirm": True}).status_code == 204
    assert client.get(frame_path).status_code == 404
    data = client.get(base + "/trace").json()
    assert data["items"][0]["before"]["availability"] == "deleted"
    assert data["items"][0]["after"]["availability"] == "retained"
    export = client.get(base + "/result/export")
    assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
    assert export.json()["counts"]["frames_deleted"] == 1
    assert "synthetic-frame" not in export.text and "storage_key" not in export.text
    assert (
        client.request("DELETE", base + "/operation-frames", json={"confirm": True}).status_code
        == 204
    )
    assert client.get(base + "/result").json()["counts"]["frames_deleted"] == 2


def test_failed_object_delete_preserves_metadata_and_commits_failure_audit(
    result_client, trace_database, monkeypatch
):
    from infrastructure.persistence.models import AuditEventModel
    from sqlalchemy import select

    client, base, root = result_client
    factory, _, _, _, store = trace_database

    def fail(_):
        raise RuntimeError("private-storage-sentinel")

    monkeypatch.setattr(store, "delete_operation_frame", fail)
    response = client.request("DELETE", base + "/operation-frames", json={"confirm": True})
    assert response.status_code == 409 and "sentinel" not in response.text
    assert client.get(base + "/trace").json()["items"][0]["before"]["availability"] == "retained"
    with factory() as reader:
        assert (
            "vision.operation_frame_delete_failed"
            in reader.scalars(select(AuditEventModel.action)).all()
        )


def test_legacy_result_is_evidence_only_without_invented_locators(result_client, trace_database):
    from infrastructure.persistence.models import VisualExplorationSessionModel

    client, base, _ = result_client
    factory, scope, _, _, _ = trace_database
    with factory.begin() as session:
        record = session.get(VisualExplorationSessionModel, scope.session_id)
        record.trace_version = "legacy"
        record.state = "completed"
    result = client.get(base + "/result").json()
    assert result["evidence_status"] == "legacy_evidence_only"
    assert result["counts"]["verified_locators"] == 0
    assert result["links"]["handoff"]["state"] == "legacy_missing"


def test_missing_or_corrupt_frame_returns_terminal_error_without_other_frame_loss(
    result_client,
    trace_database,
):
    client, base, root = result_client
    _, scope, uow, _, store = trace_database
    before = next(
        f
        for f in uow.read_snapshot(scope)["frames"]
        if f.metadata.id == root.actual_before_frame_id
    )
    store.frames[before.storage_key] = b"corrupt-private-sentinel"
    response = client.get(base + f"/operation-frames/{root.actual_before_frame_id}")
    assert response.status_code == 404 and "sentinel" not in response.text
    assert client.get(base + f"/operation-frames/{root.actual_after_frame_id}").status_code == 200


def test_project_reader_cannot_delete_operation_evidence(result_client, trace_database):
    client, base, _ = result_client
    _, scope, _, _, _ = trace_database
    app.dependency_overrides[current_principal] = lambda: Principal(
        "reader",
        {},
        {(scope.tenant_id, scope.project_id): frozenset({Role.VIEWER})},
    )
    assert client.get(base + "/trace").status_code == 200
    assert (
        client.request("DELETE", base + "/operation-frames", json={"confirm": True}).status_code
        == 404
    )


@pytest.mark.parametrize(
    "report_status", [None, "completed", "unavailable", "foreign_run", "pending"]
)
def test_result_links_follow_scoped_request_draft_run_and_report(
    result_client, trace_database, report_status
):
    from auto_at.contracts.generation import VisionPlanningSource, vision_generation_key
    from auto_at.contracts.vision import VisualHandoffBranch, VisualHandoffStep
    from infrastructure.persistence.models import (
        GeneratedTestDraftModel,
        GenerationRequestModel,
        OutboxEventModel,
        RunReportModel,
    )
    from infrastructure.persistence.models import (
        TestCaseModel as CaseModel,
    )
    from infrastructure.persistence.models import (
        TestRunModel as RunModel,
    )
    from infrastructure.persistence.repositories import SqlAlchemyGenerationRepository
    from vision_trace_fixtures import handoff

    client, base, root = result_client
    factory, scope, uow, lease, _ = trace_database
    package = handoff(
        scope,
        branches=(
            VisualHandoffBranch(
                id=uuid4(),
                status="ready",
                steps=(VisualHandoffStep(operation_id=root.id),),
            ),
        ),
    )
    uow.commit_handoff(lease, package)
    request_id, draft_id, run_id = uuid4(), uuid4(), uuid4()
    with factory.begin() as session:
        SqlAlchemyGenerationRepository(session).add_request(
            GenerationRequestModel(
                id=request_id,
                tenant_id=scope.tenant_id,
                project_id=scope.project_id,
                correlation_id=uuid4(),
                target_url="https://fixture.test/",
                redacted_request="Explore",
                request_hash="a" * 64,
                state="completed",
                vision_handoff_id=package.id,
                idempotency_key=vision_generation_key(
                    VisionPlanningSource(
                        session_id=scope.session_id,
                        handoff_id=package.id,
                        handoff_hash=package.content_hash,
                    ),
                    "Explore",
                ),
            )
        )
        session.add(
            CaseModel(
                id=str(uuid4()),
                tenant_id=scope.tenant_id,
                project_id=scope.project_id,
                target_type="web_ui",
                revision="a" * 64,
            )
        )
        session.flush()
        case = session.query(CaseModel).one()
        session.add(
            RunModel(
                id=run_id,
                tenant_id=scope.tenant_id,
                project_id=scope.project_id,
                test_case_id=case.id,
                revision="a" * 64,
                status="failed",
                correlation_id=uuid4(),
            )
        )
        session.flush()
        session.add(
            GeneratedTestDraftModel(
                id=draft_id,
                tenant_id=scope.tenant_id,
                planning_request_id=request_id,
                correlation_id=uuid4(),
                state="approved",
                title="Fixture",
                playwright_test_source="fixture",
                source_hash="a" * 64,
                assumptions=[],
                stop_conditions=[],
                provenance={},
                linked_run_id=run_id if report_status != "foreign_run" else uuid4(),
            )
        )
        if report_status == "pending":
            session.add(
                OutboxEventModel(
                    id=uuid4(),
                    tenant_id=scope.tenant_id,
                    event_type="agent.run_report.requested.v1",
                    schema_version="v1",
                    correlation_id=uuid4(),
                    idempotency_key=f"run-report:{run_id}:v1",
                    payload={"run_id": str(run_id)},
                )
            )
        if report_status in {"completed", "unavailable"}:
            session.add(
                RunReportModel(
                    id=uuid4(),
                    tenant_id=scope.tenant_id,
                    run_id=run_id,
                    correlation_id=uuid4(),
                    report_version=1,
                    schema_version="v1",
                    prompt_version="fixture",
                    deterministic_status="failed",
                    status=report_status,
                    payload=None,
                    provenance={},
                    input_hash="a" * 64,
                    created_at=datetime.now(UTC),
                )
            )
    links = client.get(base + "/result").json()["links"]
    assert links["draft"]["href"] == f"/agent?draft={draft_id}"
    if report_status == "foreign_run":
        assert links["run"]["state"] == "unavailable" and links["run"]["id"] is None
    else:
        assert links["run"]["href"] == f"/runs/{run_id}"
        assert links["report"]["state"] == (
            "available"
            if report_status == "completed"
            else "pending"
            if report_status == "pending"
            else "unavailable"
        )
