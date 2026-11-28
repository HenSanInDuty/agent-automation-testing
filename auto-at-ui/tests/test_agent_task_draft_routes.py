"""ADR-047 phase B7: `POST /vision/explorations/{id}/test-draft` over a real agent-loop session.

The session is made by the real agent loop (fake worker) on the disposable PostgreSQL fixture
(127.0.0.1:55437, skipped when absent), so "nothing changed after a refusal" is a row count and
"the value is only where it may be" is a scan of every column of every table, plus the captured
logs and every response, not an assertion about two tables.
"""

import json
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import generation, runs
from api.v1.routes import vision as routes
from config import Settings, get_settings
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    AuditEventModel,
    Base,
    GeneratedTestDraftModel,
    GenerationRequestModel,
    OutboxEventModel,
    ProjectExecutionPolicyModel,
    TestCaseModel,
    TestRunModel,
    VisualExplorationSessionModel,
    VisualOperationFrameModel,
)
from infrastructure.persistence.repositories import SqlAlchemyAuditEventRepository
from infrastructure.runners import RunnerUnavailableError
from main import app
from sqlalchemy import func, select, update
from test_vision_agent_loop import (
    DONE,
    FakeWorker,
    Outcome,
    click,
    ended,
    run_agent,
    step,
    typed,
    wait,
)

pytest_plugins = ["vision_trace_fixtures"]

NAME = "ZQ7731-name-val1"  # 16 chars
PASSWORD = "ZQ9042-word-val2"  # 16 chars: the lengths the agent typed
VALUES = [NAME, PASSWORD]
MARKERS = ("ZQ7731", "ZQ9042")
ORIGIN = "https://app.test"
REQUESTER = "requester-1"
SERVICE_TABLES = (GenerationRequestModel, GeneratedTestDraftModel, TestCaseModel, TestRunModel,
                  OutboxEventModel, AuditEventModel)

# Where the typed value may be stored, by (table, column): the draft source straight after the
# request, and the places the source follows after approval (ADR-047 "Giá trị test (Q1)" 1-4).
# A new place that stores a value is a new entry here, decided on purpose, or this test fails.
ALLOWED_AFTER_CREATE = {("generated_test_drafts", "playwright_test_source")}
ALLOWED_AFTER_APPROVAL = ALLOWED_AFTER_CREATE | {
    ("test_cases", "specification"),
    ("test_runs", "request"),
    ("outbox_events", "payload"),
}


class Preflight:
    fail = False

    def __init__(self, *_):
        pass

    def preflight(self, _request):
        if Preflight.fail:
            raise RunnerUnavailableError("generated source failed Playwright preflight")


def agent_session(disposable_database, monkeypatch):
    """Real loop, fake worker: type, type, click (the page changes, so the wait is skipped)."""

    def plan(request, ordinal):
        return Outcome(url_change="changed") if request.action.kind == "click" else Outcome()

    outputs = [
        step(typed("1:2", "a" * len(NAME)), typed("1:3", "b" * len(PASSWORD)), click("1:6"),
             wait()),
        DONE,
    ]
    worker = FakeWorker(None, None, plan=plan)
    run = run_agent(disposable_database, monkeypatch, outputs, worker=worker)
    assert run.error is None and ended(run) == "agent_done"
    return run


def principal(roles, subject=REQUESTER, tenant=None, service=False):
    return Principal(subject, {tenant: frozenset(roles)}, {}, service)


@pytest.fixture
def world(disposable_database, monkeypatch):
    run = agent_session(disposable_database, monkeypatch)
    factory, scope = run.factory, run.scope
    with factory.begin() as db:
        db.execute(update(ProjectExecutionPolicyModel).values(vision_owned_test_target=True))
    Preflight.fail = False
    for module in (routes, generation, runs):
        monkeypatch.setattr(module, "create_session_factory", lambda _settings: factory)
    monkeypatch.setattr(generation, "HttpPlaywrightTransport", Preflight)
    state = SimpleNamespace(
        factory=factory, scope=scope, tenant=scope.tenant_id, session_id=scope.session_id,
        principal=principal({Role.CONTRIBUTOR}, tenant=scope.tenant_id), seen=[],
    )
    app.dependency_overrides[current_tenant] = lambda: state.tenant
    app.dependency_overrides[current_principal] = lambda: state.principal
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, codex_bridge_enabled=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        state.client = client
        yield state
    for dependency in (current_tenant, current_principal, get_settings):
        app.dependency_overrides.pop(dependency, None)


def post(world, values=VALUES, *, key="key-1", session_id=None, **kwargs):
    kwargs.setdefault("json", {"values": values})
    kwargs.setdefault("headers", {"Idempotency-Key": key})
    response = world.client.post(
        f"/api/v1/vision/explorations/{session_id or world.session_id}/test-draft", **kwargs)
    world.seen.append(response.text)  # every response the scans must find clean
    return response


def counts(world) -> dict[str, int]:
    with world.factory() as db:
        return {m.__tablename__: db.scalar(select(func.count()).select_from(m))
                for m in SERVICE_TABLES}


def where_is(world, needle) -> set[tuple[str, str]]:
    """Every (table, column) of the whole database whose stored value contains `needle`."""
    found = set()
    with world.factory() as db:
        for table in Base.metadata.sorted_tables:
            for row in db.execute(table.select()).mappings():
                for column, value in row.items():
                    if needle in json.dumps(value, default=str):
                        found.add((table.name, column))
    return found


def set_session(world, **values):
    with world.factory.begin() as db:
        db.execute(update(VisualExplorationSessionModel).values(**values))


def decide(world, draft_id, *, subject="reviewer-1", roles=(Role.REVIEWER,), **body):
    world.principal = principal(set(roles), subject, world.tenant)
    return world.client.post(
        f"/api/v1/test-generations/drafts/{draft_id}/decision",
        json={"approved": True, "acknowledge_disposable_credentials": True, **body})


# ----------------------------------------------------------------------- the created draft


def test_the_route_creates_a_pending_review_draft_and_answers_identity_only(world):
    before = counts(world)
    response = post(world)
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"request_id", "draft_id", "correlation_id", "state", "title",
                         "source_hash", "contains_test_values", "owned_test_target", "created"}
    assert (body["state"], body["created"]) == ("pending_review", True)
    assert body["contains_test_values"] is True and body["owned_test_target"] is True
    assert "playwright_test_source" not in body
    after = counts(world)
    assert after["generation_requests"] == before["generation_requests"] + 1
    assert after["generated_test_drafts"] == before["generated_test_drafts"] + 1
    assert after["audit_events"] == before["audit_events"] + 2


def test_the_draft_is_pending_review_with_no_test_case_no_run_and_no_outbox_event(world):
    before = counts(world)
    draft_id = post(world).json()["draft_id"]
    after = counts(world)
    for table in ("test_cases", "test_runs", "outbox_events"):
        assert after[table] == before[table], table
    draft = world.client.get(f"/api/v1/test-generations/drafts/{draft_id}").json()
    assert draft["state"] == "pending_review"
    assert (draft["linked_test_case_id"], draft["linked_run_id"]) == (None, None)
    source = draft["playwright_test_source"]
    assert source.index(NAME) < source.index(PASSWORD)
    assert draft["provenance"]["agent_trace_source"]["session_id"] == str(world.session_id)
    assert draft["provenance"]["requested_by"] == REQUESTER
    assert draft["provenance"]["owned_test_target"] is True
    assert draft["provenance"]["consistency"]["assessed_sessions"] == 1


def test_the_request_row_and_both_audit_events_name_the_requester(world):
    body = post(world).json()
    with world.factory() as db:
        request = db.get(GenerationRequestModel, body["request_id"])
        assert request.state == "completed" and request.vision_handoff_id is None
        assert request.redacted_request == (
            "Deterministic draft rendered from a completed agent-loop session trace.")
        events = db.scalars(select(AuditEventModel).where(
            AuditEventModel.entity_id == request.id).order_by(AuditEventModel.action)).all()
    assert [(e.action, e.actor) for e in events] == [
        ("generation.completed", REQUESTER), ("generation.requested", REQUESTER)]
    assert {str(e.correlation_id) for e in events} == {body["correlation_id"]}


# ----------------------------------------------------------------------- idempotency


def test_asking_again_returns_the_same_draft_whatever_the_key_or_the_values(world):
    first = post(world, key="a").json()
    before = counts(world)
    for key, values in (("a", VALUES), ("b", VALUES), ("c", []), ("d", ["z" * 16, "y" * 16])):
        again = post(world, values, key=key)
        assert again.status_code == 200 and again.json()["created"] is False
        assert again.json()["draft_id"] == first["draft_id"]
    assert counts(world) == before


def test_a_key_that_belongs_to_another_request_is_409_and_writes_nothing(world):
    post(world)
    with world.factory.begin() as db:
        db.execute(update(GenerationRequestModel).values(target_url="https://elsewhere.test/"))
    before = counts(world)
    response = post(world, key="other")
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "idempotency_key_conflict"}
    assert counts(world) == before


def test_the_client_key_is_required_but_never_stored(world):
    assert post(world, headers={}).status_code == 422
    assert counts(world)["generation_requests"] == 0
    assert post(world, key="keymark-9f3a").status_code == 201
    assert where_is(world, "keymark-9f3a") == set()


# ----------------------------------------------------------------------- refusals write nothing


def assert_refused(world, response, status_code, code):
    assert response.status_code == status_code, response.text
    assert response.json()["detail"]["code"] == code
    return response.json()["detail"]


def test_a_session_that_is_not_finished_is_409(world):
    set_session(world, state="running")
    before = counts(world)
    assert_refused(world, post(world), 409, "session_not_completed")
    assert counts(world) == before


@pytest.mark.parametrize("status", ["not_achieved", "blocked", "inconclusive"])
def test_a_session_that_did_not_achieve_the_task_gets_no_draft(world, status):
    with world.factory() as db:
        stored = dict(db.scalar(select(VisualExplorationSessionModel.task_assessment)))
    set_session(world, task_assessment=stored | {"status": status})
    assert_refused(world, post(world), 409, "assessment_not_achieved")
    assert counts(world)["generation_requests"] == 0


def test_a_session_without_an_assessment_is_assessment_unavailable(world):
    set_session(world, task_assessment=None)
    assert_refused(world, post(world), 409, "assessment_unavailable")


def test_an_inconsistent_group_is_409_and_the_report_is_in_the_answer(world):
    with world.factory.begin() as db:
        source = db.scalar(select(VisualExplorationSessionModel))
        for _ in range(1):
            db.add(VisualExplorationSessionModel(**{
                column.name: getattr(source, column.name)
                for column in VisualExplorationSessionModel.__table__.columns
                if column.name not in {"id", "idempotency_key", "task_assessment"}
            } | {"id": uuid4(), "idempotency_key": uuid4().hex,
                 "task_assessment": {"status": "not_achieved", "advisory": True}}))
    detail = assert_refused(world, post(world), 409, "assessment_inconsistent")
    assert detail["consistency"]["agreement_rate"] == 0.5
    assert counts(world)["generation_requests"] == 0


def test_a_project_without_the_owned_test_target_flag_is_409(world):
    with world.factory.begin() as db:
        db.execute(update(ProjectExecutionPolicyModel).values(vision_owned_test_target=False))
    assert_refused(world, post(world), 409, "input_value_not_allowed")
    assert counts(world)["generation_requests"] == 0


def test_an_origin_outside_the_allowlist_is_409(world):
    with world.factory.begin() as db:
        db.execute(update(ProjectExecutionPolicyModel).values(
            allowed_origins=["https://other.test"]))
    assert_refused(world, post(world), 409, "origin_not_allowed")


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ([NAME], "input_value_missing"),
        ([], "input_value_missing"),
        ([NAME, PASSWORD[:-1]], "input_value_mismatch"),
        ([NAME, PASSWORD, "extra"], "input_value_mismatch"),
    ],
)
def test_missing_or_mismatching_values_are_422_with_the_step_and_without_the_value(
    world, values, code,
):
    detail = assert_refused(world, post(world, values), 422, code)
    assert set(detail) <= {"code", "step_index", "operation_id"}
    assert counts(world)["generation_requests"] == 0


def test_the_missing_value_error_names_the_step(world):
    detail = assert_refused(world, post(world, [NAME]), 422, "input_value_missing")
    assert detail["step_index"] == 1 and detail["operation_id"]


def test_evidence_that_is_gone_is_409_evidence_expired(world):
    with world.factory.begin() as db:
        db.execute(update(VisualOperationFrameModel).values(deleted_at=func.now()))
    assert_refused(world, post(world), 409, "evidence_expired")
    assert counts(world)["generation_requests"] == 0


# ----------------------------------------------------------------------- who may ask


@pytest.mark.parametrize(
    "roles", [{Role.VIEWER}, {Role.REVIEWER}, {Role.SERVICE}],
)
def test_without_submit_generation_the_answer_is_404_and_nothing_is_written(world, roles):
    world.principal = principal(roles, tenant=world.tenant, service=Role.SERVICE in roles)
    response = post(world)
    assert response.status_code == 404 and "code" not in response.text
    assert counts(world)["generation_requests"] == 0


def test_another_tenant_or_project_or_session_is_404(world):
    world.tenant = "tenant-b"
    world.principal = principal({Role.TENANT_ADMIN}, tenant="tenant-b")
    assert post(world).status_code == 404
    world.tenant = world.scope.tenant_id
    world.principal = Principal(REQUESTER, {}, {
        (world.tenant, uuid4()): frozenset({Role.PROJECT_ADMIN})})
    assert post(world).status_code == 404
    world.principal = principal({Role.CONTRIBUTOR}, tenant=world.tenant)
    assert post(world, session_id=uuid4()).status_code == 404
    assert counts(world)["generation_requests"] == 0


def test_a_session_cookie_without_the_csrf_token_is_403_before_anything_else(world):
    world.client.cookies.set("auto_at_session", "synthetic-session")
    response = post(world)
    world.client.cookies.clear()
    assert response.status_code == 403
    assert counts(world)["generation_requests"] == 0


# ----------------------------------------------------------------------- bad bodies never echo


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": {"values": NAME}},
        {"json": {"values": [NAME, 7]}},
        {"json": {"values": VALUES, "note": NAME}},
        {"json": [NAME]},
        {"json": NAME},
        {"content": '{"values": ["' + NAME + '", ', "headers": {
            "Idempotency-Key": "k", "Content-Type": "application/json"}},
    ],
)
def test_a_malformed_body_is_422_and_no_error_echoes_a_value(world, kwargs):
    response = post(world, **kwargs)
    assert response.status_code == 422
    for marker in (NAME, *MARKERS):
        assert marker not in response.text
    assert counts(world)["generation_requests"] == 0


# ----------------------------------------------------------------------- one transaction


def test_a_failure_after_the_request_and_draft_were_written_leaves_nothing_behind(
    world, monkeypatch,
):
    class FailingSecondAudit(SqlAlchemyAuditEventRepository):
        appended = 0

        def append(self, event):
            type(self).appended += 1
            if type(self).appended == 2:
                raise RuntimeError("audit store down")
            super().append(event)

    monkeypatch.setattr(routes, "SqlAlchemyAuditEventRepository", FailingSecondAudit)
    before = counts(world)
    response = post(world)
    assert response.status_code == 500 and FailingSecondAudit.appended == 2
    assert counts(world) == before  # no orphan request, no draft, no first audit event
    monkeypatch.setattr(routes, "SqlAlchemyAuditEventRepository", SqlAlchemyAuditEventRepository)
    assert post(world, key="again").status_code in {200, 201}


# ------------------------------------------------------ the value stays in the source


def test_the_value_is_only_in_the_draft_source_after_the_request(world):
    assert post(world).status_code == 201
    for value in (NAME, PASSWORD, *MARKERS):
        assert where_is(world, value) == ALLOWED_AFTER_CREATE, value
    assert not any(marker in text for text in world.seen for marker in (NAME, PASSWORD, *MARKERS))


def test_a_new_place_that_stores_the_value_makes_the_scan_fail(world):
    post(world)
    with world.factory.begin() as db:
        db.execute(update(AuditEventModel).values(actor=f"leak-{NAME}"))
    assert where_is(world, NAME) != ALLOWED_AFTER_CREATE
    assert ("audit_events", "actor") in where_is(world, NAME)


def test_after_approval_the_value_is_exactly_where_adr_047_says(world):
    draft_id = post(world).json()["draft_id"]
    assert decide(world, draft_id).status_code == 200
    for value in (NAME, PASSWORD):
        assert where_is(world, value) == ALLOWED_AFTER_APPROVAL, value
    draft = world.client.get(f"/api/v1/test-generations/drafts/{draft_id}").json()
    assert NAME in draft["playwright_test_source"]
    run = world.client.get(f"/api/v1/runs/{draft['linked_run_id']}").json()
    assert NAME in run["playwright_test_source"]
    assert not any(NAME in text for text in world.seen)  # the create/refusal answers stay clean
    with world.factory() as db:
        case = db.scalars(select(TestCaseModel)).one()
        assert case.specification["contains_test_values"] is True


def test_no_log_record_and_no_output_holds_a_value(world, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    post(world, [NAME[:-1], PASSWORD])        # 422: mismatch
    post(world, json={"values": NAME})          # 422: malformed
    post(world, json={"values": VALUES}, key="x")  # 201
    post(world, key="y")                        # 200: replay
    set_session(world, state="running")
    post(world, key="z")                        # 409
    with world.factory.begin() as db:
        db.execute(update(AuditEventModel).values(actor="x"))
    assert caplog.records, "the middleware logs every request; an empty capture proves nothing"
    logged = "\n".join(
        record.getMessage() + repr(record.__dict__) + (record.exc_text or "")
        for record in caplog.records)
    out, err = capfd.readouterr()
    for secret in (NAME, PASSWORD, *MARKERS):
        assert secret not in logged and secret not in out and secret not in err


def test_a_server_error_does_not_leak_the_value_to_the_client_or_the_log(
    world, monkeypatch, caplog,
):
    caplog.set_level(logging.DEBUG)

    def boom(self, **_kwargs):
        raise RuntimeError("downstream failure")

    monkeypatch.setattr(routes.CreateAgentTaskDraft, "execute", boom)
    response = post(world)
    assert response.status_code == 500
    logged = "\n".join(
        r.getMessage() + repr(r.__dict__) + (r.exc_text or "") for r in caplog.records)
    for secret in (NAME, PASSWORD, *MARKERS):
        assert secret not in response.text and secret not in logged
