"""QA phase 09: independent behavioural checks of the consistency report endpoint.

New cases only (the developer module is not imported). DB/HTTP cases use the PostgreSQL fixture
on 127.0.0.1:55437 with hand-inserted rows.
"""

import json
import random
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import vision as routes
from application.agent_task_consistency import summarise_group
from config import Settings
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    Base,
    ProjectModel,
    VisualExplorationSessionModel,
)
from main import app
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from vision_trace_fixtures import session_values

pytest_plugins = ["vision_trace_fixtures"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark/task_ui"))
import stability  # noqa: E402

URL = "https://fixture.test/"
HASH = "b" * 64
TENANT = "tenant-a"
STATUSES = ("achieved", "not_achieved", "blocked", "inconclusive")


class World:
    """Rows of one disposable database plus helpers to add sessions."""

    def __init__(self, engine):
        Base.metadata.create_all(engine)
        self.factory = sessionmaker(engine, expire_on_commit=False)
        self.project, self.other_project = uuid4(), uuid4()
        self.n = 0
        with self.factory.begin() as db:
            for tenant, pid in ((TENANT, self.project), (TENANT, self.other_project),
                                ("tenant-b", uuid4())):
                db.add(ProjectModel(id=pid, tenant_id=tenant, name="P", default_target="web_ui"))

    def add(self, status="achieved", *, state="completed", engine="agent_loop", pid=None,
            tid=TENANT, url=URL, intent=HASH, assessment="auto"):
        self.n += 1
        scope = type("S", (), {"session_id": uuid4(), "tenant_id": tid,
                               "project_id": pid or self.project})
        if assessment == "auto":
            assessment = {"status": status, "advisory": True} if status else None
        with self.factory.begin() as db:
            if tid == "tenant-b" and pid is None:
                scope.project_id = db.scalar(select(ProjectModel.id).where(
                    ProjectModel.tenant_id == "tenant-b"))
            db.add(VisualExplorationSessionModel(**session_values(
                scope, state=state, exploration_engine=engine, target_url=url,
                intent_hash=intent, task_assessment=assessment,
                created_at=datetime.now(UTC) + timedelta(seconds=self.n))))
        return scope.session_id

    def many(self, statuses):
        return [self.add(s) for s in statuses]


@pytest.fixture
def world(disposable_database):
    return World(disposable_database)


def viewer(world, tenant=TENANT):
    return Principal("reader", {}, {(tenant, world.project): frozenset({Role.VIEWER})})


@pytest.fixture
def http(world, monkeypatch):
    monkeypatch.setattr(routes, "create_session_factory", lambda _: world.factory)
    app.dependency_overrides[current_tenant] = lambda: TENANT
    app.dependency_overrides[current_principal] = lambda: viewer(world)
    try:
        yield TestClient(app)
    finally:
        for key in (current_tenant, current_principal, routes.get_settings):
            app.dependency_overrides.pop(key, None)


def get(http, sid):
    return http.get(f"/api/v1/vision/explorations/{sid}/consistency")


def use_threshold(value):
    app.dependency_overrides[routes.get_settings] = lambda: Settings(
        agent_task_consistency_threshold=value)


# ------------------------------------------------------------------ AC1 404 / auth
def comparable(response):
    volatile = ("date", "x-correlation-id", "traceparent")
    headers = {k: v for k, v in response.headers.items() if k not in volatile}
    return response.status_code, response.content, headers


def test_ac1_all_denials_are_byte_identical_to_not_found(http, world):
    ids = world.many(["achieved"] * 3)
    baseline = comparable(get(http, uuid4()))
    assert baseline[0] == 404
    callers = {
        "no_grants": Principal("r", {}, {}),
        "foreign_project": Principal("r", {}, {(TENANT, uuid4()): frozenset({Role.VIEWER})}),
        "foreign_tenant_admin": Principal("r", {"elsewhere": frozenset({Role.TENANT_ADMIN})}, {}),
        "service": Principal("w", {TENANT: frozenset({Role.TENANT_ADMIN})}, {}, is_service=True),
        "service_project": Principal(
            "w", {}, {(TENANT, world.project): frozenset({Role.SERVICE})}, is_service=True),
    }
    for name, principal in callers.items():
        app.dependency_overrides[current_principal] = lambda p=principal: p
        assert comparable(get(http, ids[0])) == baseline, name


def test_ac1_session_of_another_tenant_is_not_found_and_identical(http, world):
    foreign = world.add(tid="tenant-b")
    assert comparable(get(http, foreign)) == comparable(get(http, uuid4()))


def test_ac1_success_has_no_store_and_each_role_with_read_gets_200(http, world):
    sid = world.many(["achieved"] * 3)[0]
    for role in (Role.VIEWER, Role.CONTRIBUTOR, Role.REVIEWER, Role.PROJECT_ADMIN):
        principal = Principal("r", {}, {(TENANT, world.project): frozenset({role})})
        app.dependency_overrides[current_principal] = lambda p=principal: p
        response = get(http, sid)
        assert response.status_code == 200, role
        assert response.headers["cache-control"] == "private, no-store"


def test_ac1_a_bad_uuid_is_422_not_a_500(http):
    assert http.get("/api/v1/vision/explorations/not-a-uuid/consistency").status_code == 422


def test_ac1_response_carries_no_task_text_or_urls(http, world):
    sid = world.many(["achieved"] * 3)[0]
    text = get(http, sid).text
    assert URL not in text and "fixture-ciphertext" not in text and HASH not in text


# ------------------------------------------------------------------ group isolation
def test_group_excludes_other_tenant_project_url_intent_and_engine(http, world):
    ids = world.many(["achieved"] * 3)
    world.add("not_achieved", tid="tenant-b")                  # other tenant, same url+hash
    world.add("not_achieved", pid=world.other_project)         # other project
    world.add("not_achieved", url="https://fixture.test/x")    # other url
    world.add("not_achieved", url=URL.upper())                 # url differing by case
    world.add("not_achieved", intent="c" * 64)                 # other intent, same url
    world.add("not_achieved", engine="planner")                # other engine
    data = get(http, ids[0]).json()
    assert data["group_sessions"] == 3 and data["assessed_sessions"] == 3
    assert data["status_counts"]["not_achieved"] == 0 and data["eligible"] is True


# ------------------------------------------------------------------ denominator
@pytest.mark.parametrize("kind", [
    dict(status=None, state="unavailable"),
    dict(status="achieved", state="unavailable"),
    dict(status="achieved", state="running"),
    dict(status="achieved", state="cancelled"),
    dict(status="achieved", state="failed"),
    dict(status=None),                                        # completed, no assessment
    dict(status="exotic"),                                    # unknown status
    dict(status="ACHIEVED"),                                  # case differs
    dict(status="achieved", assessment="a string"),           # not a dict
    dict(status="achieved", assessment={}),                   # dict without status
    dict(status="achieved", assessment={"status": None}),
    pytest.param(
        dict(status="achieved", assessment={"status": ["achieved"]}),  # unhashable status
        marks=pytest.mark.xfail(strict=True, reason=(
            "QA note (non-blocking): agent_task_consistency.py:80 `status in frozenset` raises "
            "TypeError on a non-hashable status -> HTTP 500; unreachable via the write path"))),
])
def test_denominator_ignores_unassessed_or_unfinished_sessions(http, world, kind):
    ids = world.many(["achieved"] * 3)
    kind = dict(kind)
    kw = {k: v for k, v in kind.items() if k != "status"}
    world.add(kind.get("status"), **kw)
    response = get(http, ids[0])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["assessed_sessions"] == 3 and data["group_sessions"] == 4
    assert data["agreement_rate"] == 1.0 and data["eligible"] is True


def test_source_without_assessment_is_refused_not_crashing(http, world):
    world.many(["achieved"] * 5)
    for source in (world.add(None, state="unavailable"), world.add(None)):
        data = get(http, source).json()
        assert data["source_status"] is None and data["source_is_modal"] is False
        assert data["eligible"] is False and data["reasons"] == ["source_not_modal"]


def test_planner_session_as_source_is_refused(http, world):
    world.many(["achieved"] * 5)
    data = get(http, world.add("achieved", engine="planner")).json()
    assert data["eligible"] is False and "source_not_modal" in data["reasons"]


def test_group_without_any_assessed_session(http, world):
    source = world.add(None, state="unavailable")
    data = get(http, source).json()
    assert data["assessed_sessions"] == 0 and data["agreement_rate"] is None
    assert data["modal_status"] is None and data["eligible"] is False
    assert "assessment_inconsistent" in data["reasons"] and data["small_sample"] is True


# ------------------------------------------------------------------ reasons / threshold
def test_reason_assessment_inconsistent_only(http, world):
    ids = world.many(["achieved"] * 4 + ["blocked"])
    data = get(http, ids[0]).json()
    assert data["reasons"] == ["assessment_inconsistent"] and data["eligible"] is False


def test_reason_modal_not_achieved_only(http, world):
    ids = world.many(["not_achieved"] * 10)
    assert get(http, ids[0]).json()["reasons"] == ["modal_not_achieved"]


def test_reason_source_not_modal_only(http, world):
    ids = world.many(["achieved"] * 9 + ["not_achieved"])
    data = get(http, ids[-1]).json()
    assert data["agreement_rate"] == 0.9 and data["reasons"] == ["source_not_modal"]


def test_reasons_combine_all_three_in_fixed_order(http, world):
    ids = world.many(["blocked", "blocked", "achieved"])
    assert get(http, ids[2]).json()["reasons"] == [
        "modal_not_achieved", "source_not_modal", "assessment_inconsistent"]


def test_threshold_boundary_nine_of_ten_is_eligible_at_0_9_like_stability(http, world):
    ids = world.many(["achieved"] * 9 + ["blocked"])
    data = get(http, ids[0]).json()
    assert data["agreement_rate"] == 0.9 and data["eligible"] is True
    # stability.py uses `>=` for the same ratio
    task = {"id": "t", "expected_status": "achieved"}
    stats = stability._task_stats(task, [{"state": "completed", "assessment_status": s}
                                         for s in ["achieved"] * 9 + ["blocked"]])
    assert stats["agreement_rate"] >= stability.STABLE_THRESHOLD


def test_threshold_boundary_just_above_and_below(http, world):
    ids = world.many(["achieved"] * 9 + ["blocked"])
    use_threshold(0.91)
    assert get(http, ids[0]).json()["eligible"] is False
    use_threshold(0.9)
    assert get(http, ids[0]).json()["eligible"] is True
    use_threshold(1)
    assert get(http, ids[0]).json()["reasons"] == ["assessment_inconsistent"]


def test_threshold_one_requires_unanimity(http, world):
    ids = world.many(["achieved"] * 4)
    use_threshold(1.0)
    assert get(http, ids[0]).json()["eligible"] is True


def test_threshold_comes_from_env_through_settings(monkeypatch):
    monkeypatch.setenv("AGENT_TASK_CONSISTENCY_THRESHOLD", "0.75")
    assert Settings().agent_task_consistency_threshold == 0.75
    monkeypatch.delenv("AGENT_TASK_CONSISTENCY_THRESHOLD")
    assert Settings(_env_file=None).agent_task_consistency_threshold == 0.9


@pytest.mark.parametrize("bad", [0, 0.0, -0.1, -1, 1.0001, 2, 90, "abc", "nan", "inf"])
def test_invalid_threshold_is_rejected_when_building_settings(bad):
    with pytest.raises(ValidationError):
        Settings(agent_task_consistency_threshold=bad)


@pytest.mark.parametrize("bad", ["0", "-0.5", "1.5", "x"])
def test_invalid_threshold_in_env_is_rejected(monkeypatch, bad):
    monkeypatch.setenv("AGENT_TASK_CONSISTENCY_THRESHOLD", bad)
    with pytest.raises(ValidationError):
        Settings()


# ------------------------------------------------------------------ distribution
def test_four_achieved_one_not_achieved_shows_everything_and_is_not_eligible(http, world):
    ids = world.many(["achieved"] * 4 + ["not_achieved"])
    data = get(http, ids[0]).json()
    assert data["status_counts"] == {"achieved": 4, "blocked": 0, "inconclusive": 0,
                                     "not_achieved": 1}
    assert data["agreement_rate"] == 0.8 and data["eligible"] is False
    assert data["modal_status"] == "achieved" and data["modal_count"] == 4
    assert list(data["status_counts"]) == sorted(STATUSES)  # always all four keys


def test_modal_tie_is_deterministic_and_repeatable(http, world):
    ids = world.many(["not_achieved", "achieved", "not_achieved", "achieved"])
    seen = {json.dumps(get(http, ids[0]).json(), sort_keys=True) for _ in range(5)}
    assert len(seen) == 1
    data = json.loads(seen.pop())
    assert data["modal_status"] == "achieved" and data["agreement_rate"] == 0.5
    assert data["eligible"] is False


def test_tie_result_does_not_depend_on_insertion_order(world):
    forward = summarise_group("achieved", ["achieved", "not_achieved"] * 2, 0.9)
    backward = summarise_group("achieved", ["not_achieved", "achieved"] * 2, 0.9)
    assert forward == backward


def test_single_session_is_100_percent_with_small_sample_flag(http, world):
    sid = world.add("achieved")
    data = get(http, sid).json()
    assert data["agreement_rate"] == 1.0 and data["assessed_sessions"] == 1
    assert data["small_sample"] is True and data["group_sessions"] == 1


def test_two_sessions_are_still_small_three_are_not(http, world):
    ids = world.many(["achieved"] * 2)
    assert get(http, ids[0]).json()["small_sample"] is True
    world.add("achieved")
    assert get(http, ids[0]).json()["small_sample"] is False


def test_large_group(http, world):
    ids = world.many(["achieved"] * 120 + ["blocked"] * 30)
    data = get(http, ids[0]).json()
    assert data["assessed_sessions"] == 150 and data["agreement_rate"] == 0.8


# ------------------------------------------------------------------ formula vs benchmark
@pytest.mark.parametrize("seed", range(40))
def test_random_distributions_match_benchmark_stability(seed):
    rng = random.Random(seed)
    size = rng.randint(1, 25)
    weights = [rng.random() for _ in STATUSES]
    statuses = rng.choices(STATUSES, weights, k=size)
    runs = [{"state": "completed", "assessment_status": s} for s in statuses]
    expected = stability._task_stats({"id": "t", "expected_status": "achieved"}, runs)
    got = summarise_group(statuses[0], statuses, stability.STABLE_THRESHOLD)
    assert got["agreement_rate"] == expected["agreement_rate"]
    assert got["modal_status"] == expected["modal_status"]
    assert got["modal_count"] == expected["modal_count"]
    assert got["assessed_sessions"] == expected["assessed"]
    assert {k: v for k, v in got["status_counts"].items() if v} == expected["status_counts"]
    stable = expected["agreement_rate"] >= stability.STABLE_THRESHOLD
    assert ("assessment_inconsistent" not in got["reasons"]) is stable


def test_control_plane_does_not_import_benchmark_task_ui():
    pattern = re.compile(r"^\s*(from|import)\s+(stability|benchmark\.task_ui|task_ui)\b", re.M)
    for name in ("application/agent_task_consistency.py", "api/v1/routes/vision.py",
                 "infrastructure/persistence/repositories.py", "config.py"):
        source = (ROOT / "apps/control-plane" / name).read_text(encoding="utf-8")
        assert not pattern.search(source), name
    assert "STABLE_THRESHOLD" not in (
        ROOT / "apps/control-plane/application/agent_task_consistency.py").read_text("utf-8")


def test_only_config_reads_environment_for_the_threshold():
    base = ROOT / "apps/control-plane"
    for name in ("application/agent_task_consistency.py", "api/v1/routes/vision.py"):
        assert "environ" not in (base / name).read_text("utf-8") and "getenv" not in (
            base / name).read_text("utf-8"), name


# ------------------------------------------------------------------ wording
def test_response_never_claims_verification(http, world):
    ids = world.many(["achieved"] * 5)
    text = get(http, ids[0]).text.lower()
    for word in ("verified", "xác minh", "đã kiểm chứng", "validated", "proven"):
        assert word not in text, word
    assert "not proof" in text and "advisory" in text


# ------------------------------------------------------------------ read only
def snapshot(world):
    with world.factory() as db:
        rows = db.execute(select(
            VisualExplorationSessionModel.id, VisualExplorationSessionModel.updated_at,
            VisualExplorationSessionModel.state, VisualExplorationSessionModel.task_assessment,
        ).order_by(VisualExplorationSessionModel.id)).all()
        return [tuple(map(str, r)) for r in rows]


def test_get_writes_nothing(http, world):
    ids = world.many(["achieved"] * 4 + ["not_achieved"])
    before = snapshot(world)
    with world.factory() as db:
        count = db.scalar(select(func.count()).select_from(VisualExplorationSessionModel))
    for sid in ids + [uuid4()]:
        get(http, sid)
    assert snapshot(world) == before
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(VisualExplorationSessionModel)) == count


def test_route_is_get_only(http, world):
    sid = world.add("achieved")
    for method in ("post", "put", "patch", "delete"):
        response = getattr(http, method)(f"/api/v1/vision/explorations/{sid}/consistency")
        assert response.status_code in (404, 405, 403, 422), (method, response.status_code)
    assert "achieved" in snapshot(world)[0][3]
