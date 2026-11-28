"""ADR-047 phase B2: consistency report over sessions of the same task.

Pure cases cover the arithmetic and the refusal reasons; HTTP and scope cases use the PostgreSQL
fixture (127.0.0.1:55437) with hand-inserted session rows.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import vision as routes
from application.agent_task_consistency import (
    SMALL_SAMPLE_SESSIONS,
    read_consistency,
    summarise_group,
)
from application.vision_replay import VisionReplayNotFoundError
from config import Settings
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    Base,
    ProjectModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.repositories import SqlAlchemyVisionRepository
from main import app
from sqlalchemy.orm import sessionmaker
from vision_trace_fixtures import session_values

pytest_plugins = ["vision_trace_fixtures"]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmark/task_ui"))
import stability  # noqa: E402

URL = "https://fixture.test/"
HASH = "b" * 64


def report(source, statuses, threshold=0.9):
    return summarise_group(source, statuses, threshold)


# ---------------------------------------------------------------- pure arithmetic


def test_unanimous_achieved_is_eligible_and_lists_the_whole_distribution():
    data = report("achieved", ["achieved"] * 5)
    assert data["eligible"] is True and data["reasons"] == []
    assert data["agreement_rate"] == 1.0 and data["assessed_sessions"] == 5
    assert data["status_counts"] == {
        "achieved": 5, "blocked": 0, "inconclusive": 0, "not_achieved": 0}
    assert data["small_sample"] is False and data["advisory"] is True


def test_four_achieved_one_not_achieved_is_below_the_threshold_and_shows_the_minority():
    data = report("achieved", ["achieved"] * 4 + ["not_achieved"])
    assert data["agreement_rate"] == 0.8
    assert data["status_counts"]["not_achieved"] == 1 and data["status_counts"]["achieved"] == 4
    assert data["eligible"] is False and data["reasons"] == ["assessment_inconsistent"]
    assert data["modal_status"] == "achieved"  # the majority is reported, never silently chosen


def test_the_threshold_comes_from_the_caller_and_flips_eligible():
    statuses = ["achieved"] * 4 + ["not_achieved"]
    assert report("achieved", statuses, 0.8)["eligible"] is True
    assert report("achieved", statuses, 0.81)["eligible"] is False
    assert report("achieved", statuses, 0.9)["threshold"] == 0.9


def test_a_modal_status_other_than_achieved_is_refused():
    data = report("not_achieved", ["not_achieved"] * 5)
    assert data["agreement_rate"] == 1.0
    assert data["eligible"] is False and data["reasons"] == ["modal_not_achieved"]


def test_a_source_session_outside_the_modal_status_is_refused():
    data = report("not_achieved", ["achieved"] * 9 + ["not_achieved"])
    assert data["agreement_rate"] == 0.9 and data["source_is_modal"] is False
    assert data["eligible"] is False and data["reasons"] == ["source_not_modal"]


def test_reasons_accumulate_in_a_fixed_order():
    data = report("achieved", ["blocked", "blocked", "achieved"])
    assert data["reasons"] == ["modal_not_achieved", "source_not_modal", "assessment_inconsistent"]


def test_a_single_session_is_100_percent_but_flagged_as_a_small_sample():
    data = report("achieved", ["achieved"])
    assert data["agreement_rate"] == 1.0 and data["assessed_sessions"] == 1
    assert data["small_sample"] is True and data["eligible"] is True
    assert report("achieved", ["achieved"] * SMALL_SAMPLE_SESSIONS)["small_sample"] is False


def test_a_source_without_an_assessment_and_an_empty_group_are_refused_not_crashed():
    data = report(None, ["achieved"] * 3)
    assert data["source_status"] is None and data["reasons"] == ["source_not_modal"]
    empty = report(None, [])
    assert empty["agreement_rate"] is None and empty["modal_status"] is None
    assert empty["eligible"] is False and "assessment_inconsistent" in empty["reasons"]


def test_a_tie_goes_to_the_alphabetically_first_status():
    data = report("achieved", ["not_achieved", "achieved"])
    assert data["modal_status"] == "achieved" and data["agreement_rate"] == 0.5
    assert data["eligible"] is False


def test_the_notice_states_agreement_is_not_correctness_and_never_claims_verification():
    data = report("achieved", ["achieved"] * 5)
    assert "not proof" in data["notice"]
    text = str(data).lower()
    assert "verified" not in text and "xác minh" not in text


@pytest.mark.parametrize(
    "statuses",
    [
        ["achieved"] * 10,
        ["achieved"] * 9 + ["blocked"],
        ["achieved"] * 7 + ["not_achieved"] * 3,
        ["blocked", "achieved", "blocked", "inconclusive"],
        ["not_achieved"],
    ],
)
def test_agreement_matches_the_benchmark_stability_formula(statuses):
    task = {"id": "t", "expected_status": "achieved"}
    runs = [{"state": "completed", "assessment_status": status} for status in statuses]
    expected = stability._task_stats(task, runs)
    data = report(statuses[0], statuses)
    assert data["agreement_rate"] == expected["agreement_rate"]
    assert data["modal_status"] == expected["modal_status"]
    assert data["modal_count"] == expected["modal_count"]
    assert data["assessed_sessions"] == expected["assessed"]


def test_the_default_threshold_is_the_benchmark_one():
    assert Settings().agent_task_consistency_threshold == stability.STABLE_THRESHOLD == 0.9


# ---------------------------------------------------------------- real rows, scope and HTTP


def assessment(status):
    return {"status": status, "advisory": True}


@pytest.fixture
def group(disposable_database):
    Base.metadata.create_all(disposable_database)
    factory = sessionmaker(disposable_database, expire_on_commit=False)
    tenant, project, other_project = "tenant-a", uuid4(), uuid4()
    ids = []
    with factory.begin() as db:
        for pid in (project, other_project):
            db.add(ProjectModel(id=pid, tenant_id=tenant, name="P", default_target="web_ui"))
        db.add(ProjectModel(id=uuid4(), tenant_id="tenant-b", name="B", default_target="web_ui"))
        db.flush()
        base = datetime.now(UTC)

        def add(n, *, status="achieved", state="completed", engine="agent_loop", pid=project,
                tid=tenant, url=URL, intent=HASH):
            scope = type("S", (), {"session_id": uuid4(), "tenant_id": tid, "project_id": pid})
            row = VisualExplorationSessionModel(**session_values(
                scope, state=state, exploration_engine=engine, target_url=url, intent_hash=intent,
                task_assessment=assessment(status) if status else None,
                created_at=base + timedelta(seconds=n)))
            db.add(row)
            return scope.session_id

        ids = [add(n) for n in range(4)]                       # 4 achieved
        ids.append(add(4, status="not_achieved"))               # 1 not_achieved
        add(5, status=None, state="unavailable")                # unavailable: not counted
        add(6, status=None)                                     # completed, no assessment (legacy)
        add(7, state="running")                                 # not finished: not counted
        add(8, engine="planner")                                # planner session: not counted
        add(9, url="https://other.test/")                       # other target
        add(10, intent="c" * 64)                                # other task
        add(11, pid=other_project)                              # other project
    return factory, tenant, project, ids


@pytest.fixture
def client(group, monkeypatch):
    factory, tenant, project, ids = group
    principal = Principal("reader", {}, {(tenant, project): frozenset({Role.VIEWER})})
    monkeypatch.setattr(routes, "create_session_factory", lambda _: factory)
    app.dependency_overrides[current_tenant] = lambda: tenant
    app.dependency_overrides[current_principal] = lambda: principal
    try:
        yield TestClient(app), ids
    finally:
        app.dependency_overrides.pop(current_tenant, None)
        app.dependency_overrides.pop(current_principal, None)


def test_http_counts_only_completed_assessed_agent_loop_sessions_of_the_same_task(client):
    http, ids = client
    response = http.get(f"/api/v1/vision/explorations/{ids[0]}/consistency")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    data = response.json()
    assert data["assessed_sessions"] == 5 and data["group_sessions"] == 8
    assert data["status_counts"] == {
        "achieved": 4, "blocked": 0, "inconclusive": 0, "not_achieved": 1}
    assert data["agreement_rate"] == 0.8 and data["source_is_modal"] is True
    assert data["eligible"] is False and data["reasons"] == ["assessment_inconsistent"]
    assert data["threshold"] == 0.9 and data["advisory"] is True and data["small_sample"] is False


def test_http_a_minority_source_session_gets_source_not_modal(client):
    http, ids = client
    data = http.get(f"/api/v1/vision/explorations/{ids[4]}/consistency").json()
    assert data["source_status"] == "not_achieved" and data["source_is_modal"] is False
    assert data["reasons"] == ["source_not_modal", "assessment_inconsistent"]


def test_http_the_configured_threshold_changes_eligible(client):
    http, ids = client
    app.dependency_overrides[routes.get_settings] = lambda: Settings(
        agent_task_consistency_threshold=0.8)
    try:
        data = http.get(f"/api/v1/vision/explorations/{ids[0]}/consistency").json()
    finally:
        app.dependency_overrides.pop(routes.get_settings, None)
    assert data["threshold"] == 0.8 and data["eligible"] is True and data["reasons"] == []


@pytest.mark.parametrize("caller", ["foreign_project", "foreign_tenant", "service", "unknown"])
def test_http_hides_the_session_from_other_tenants_projects_and_unknown_ids(
    client, group, caller
):
    http, ids = client
    _, tenant, project, _ = group
    principal = {
        "foreign_project": Principal("r", {}, {(tenant, uuid4()): frozenset({Role.VIEWER})}),
        "foreign_tenant": Principal("r", {"elsewhere": frozenset({Role.TENANT_ADMIN})}, {}),
        "service": Principal("w", {tenant: frozenset({Role.TENANT_ADMIN})}, {}, is_service=True),
        "unknown": Principal("r", {}, {(tenant, project): frozenset({Role.VIEWER})}),
    }[caller]
    app.dependency_overrides[current_principal] = lambda: principal
    target = uuid4() if caller == "unknown" else ids[0]
    assert http.get(f"/api/v1/vision/explorations/{target}/consistency").status_code == 404


def test_db_scope_never_reads_sessions_of_another_tenant_or_project(group):
    factory, tenant, project, ids = group
    principal = Principal("r", {tenant: frozenset({Role.TENANT_ADMIN})}, {})
    with factory() as db:
        repo = SqlAlchemyVisionRepository(db)
        data = read_consistency(repo, tenant_id=tenant, principal=principal,
                                session_id=ids[0], threshold=0.9)
        assert data["group_sessions"] == 8
        assert repo.list_same_task("tenant-b", project, URL, HASH) == []
        assert repo.list_same_task(tenant, uuid4(), URL, HASH) == []
        with pytest.raises(VisionReplayNotFoundError):
            read_consistency(repo, tenant_id="tenant-b", principal=Principal(
                "r", {"tenant-b": frozenset({Role.TENANT_ADMIN})}, {}),
                session_id=ids[0], threshold=0.9)
