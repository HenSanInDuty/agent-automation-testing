"""ADR-047 Q1, phase 15b: `GET /vision/explorations/{id}/test-draft/inputs`.

No database: the use case and the route run over the in-memory rows and repositories of
`test_agent_task_draft.py`. The route is exercised through `TestClient` with the SQL repositories
and the transaction swapped for those fakes, so the JSON below is what a client receives.
"""

import logging
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import vision as routes
from application.agent_task_draft import (
    AgentTaskDraftNotFound,
    AgentTaskDraftRefused,
    ReadAgentTaskDraftInputs,
)
from application.agent_task_renderer import typed_steps
from application.vision_source_renderer import literal
from config import Settings, get_settings
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from main import app
from test_agent_task_draft import (
    NAME,
    PASSWORD,
    TENANT,
    VALUES,
    Trace,
    World,
    contributor,
)
from test_agent_task_trace import Rows, login_rows, stored_assessment

URL = "/api/v1/vision/explorations/{}/test-draft/inputs"


def read(world, principal=None, **options):
    return ReadAgentTaskDraftInputs(
        world.sessions, Trace(world.rows), world.generations
    ).execute(
        tenant_id=options.pop("tenant_id", TENANT),
        principal=principal or contributor(),
        session_id=options.pop("session_id", world.session.id),
    )


def refusal(world, **options) -> AgentTaskDraftRefused:
    with pytest.raises(AgentTaskDraftRefused) as caught:
        read(world, **options)
    return caught.value


# ------------------------------------------------------------------- use case


def test_the_steps_are_the_type_steps_in_the_order_the_renderer_consumes_values():
    world = World()
    result = read(world)
    trace = world.rows.build()
    assert result.owned_test_target is True
    assert result.has_type_steps is True
    assert [item[0] for item in result.type_steps] == [s.step_index for s in typed_steps(trace)]
    assert result.type_steps == tuple(
        (s.step_index, s.locator.value, s.text_chars) for s in typed_steps(trace)
    )
    assert [item[1] for item in result.type_steps] == ["Tên đăng nhập", "Mật khẩu"]
    assert [item[2] for item in result.type_steps] == [len(NAME), len(PASSWORD)]


def test_values_as_long_as_the_answer_say_are_accepted_by_the_post_use_case():
    world = World()
    values = ["v" * chars for _, _, chars in read(world).type_steps]
    assert len(values) == len(typed_steps(world.rows.build()))
    result = world.create(values)  # no input_value_mismatch / input_value_missing
    assert result.created is True


def test_one_value_more_or_less_than_the_answer_is_what_post_refuses():
    world = World()
    count = len(read(world).type_steps)
    assert world.refusal(["v" * 24] * (count - 1)).code == "input_value_missing"
    assert world.refusal(["v" * 24] * (count + 1)).code == "input_value_mismatch"


def test_a_session_without_type_steps_answers_an_empty_list_with_the_flag():
    rows = Rows()
    rows.op("navigate", purpose="setup")
    rows.step(1, rows.op("click", name="Open"))
    result = read(World(rows))
    assert (result.owned_test_target, result.type_steps, result.has_type_steps) == (
        True, (), False)


def test_a_project_without_the_flag_gets_no_length_even_with_type_steps():
    result = read(World(owned=False))
    assert (result.owned_test_target, result.type_steps, result.has_type_steps) == (
        False, (), True)


def test_flag_off_and_no_type_step_says_so_and_post_still_makes_the_draft():
    rows = Rows()
    rows.op("navigate", purpose="setup")
    rows.step(1, rows.op("click", name="Open"))
    world = World(rows, owned=False)
    result = read(world)
    assert (result.owned_test_target, result.type_steps, result.has_type_steps) == (
        False, (), False)
    assert world.create([]).created is True


def test_a_project_without_a_policy_gets_the_same_empty_answer():
    world = World()
    world.generations.policy = None
    result = read(world)
    assert (result.owned_test_target, result.type_steps, result.has_type_steps) == (
        False, (), True)


def test_it_reads_the_locator_name_that_the_renderer_puts_in_the_source():
    world = World()
    result = read(world)
    source = world.create(VALUES).draft.playwright_test_source
    for _, name, _ in result.type_steps:
        assert f"name: {literal(name)}" in source


# The same refusals as `POST`, from the same `_check_assessment` and `_read_trace`.


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"state": "running"}, "session_not_completed"),
        ({"exploration_engine": "legacy"}, "assessment_unavailable"),
        ({"task_assessment": None}, "assessment_unavailable"),
        ({"task_assessment": {"status": "surprise"}}, "assessment_unavailable"),
        ({"task_assessment": stored_assessment("blocked") | {"status": "blocked"}},
         "assessment_not_achieved"),
    ],
)
def test_a_session_that_cannot_back_a_draft_has_the_post_code(override, code):
    rows = login_rows()[0]
    world = World(rows, session=rows.session(**override))
    assert refusal(world).code == code
    assert world.refusal().code == code  # the very same code as POST


def test_gone_evidence_is_evidence_expired_and_a_trace_refusal_keeps_its_step():
    rows = login_rows()[0]
    rows.frames.pop()
    assert refusal(World(rows)).code == "evidence_expired"
    rows = Rows()
    rows.op("navigate", purpose="setup")
    broken = rows.op("click", name="Open", locator="absent")
    rows.step(1, broken)
    error = refusal(World(rows))
    assert (error.code, error.step_index, error.operation_id) == (
        "locator_unavailable", 1, broken.id)


def test_consistency_is_not_asked():
    world = World(peers=["achieved", "achieved", "achieved", "not_achieved"])
    assert world.refusal().code == "assessment_inconsistent"  # POST refuses
    assert len(read(world).type_steps) == 2  # the inputs are still readable


@pytest.mark.parametrize(
    "principal",
    [
        Principal("viewer-1", {TENANT: frozenset({Role.VIEWER})}, {}),
        Principal("reviewer-1", {TENANT: frozenset({Role.REVIEWER})}, {}),
        Principal("other-tenant", {"tenant-b": frozenset({Role.TENANT_ADMIN})}, {}),
        Principal("nobody", {}, {}),
    ],
)
def test_without_submit_generation_or_in_another_tenant_it_is_not_found(principal):
    with pytest.raises(AgentTaskDraftNotFound):
        read(World(), principal=principal)


def test_a_missing_session_and_another_tenant_are_not_found():
    world = World()
    with pytest.raises(AgentTaskDraftNotFound):
        read(world, session_id=uuid4())
    with pytest.raises(AgentTaskDraftNotFound):
        read(world, tenant_id="tenant-b", principal=contributor(tenant="tenant-b"))


def test_it_writes_nothing():
    world = World()
    read(world)
    world.assert_nothing_written()


# ----------------------------------------------------------------------- route


@contextmanager
def _no_transaction(_factory):
    yield object()


@pytest.fixture
def api(monkeypatch):
    world = World()
    state = SimpleNamespace(world=world, principal=contributor(), tenant=TENANT)
    monkeypatch.setattr(routes, "create_session_factory", lambda _settings: None)
    monkeypatch.setattr(routes, "transactional_session", _no_transaction)
    monkeypatch.setattr(routes, "SqlAlchemyVisionRepository", lambda _s: state.world.sessions)
    monkeypatch.setattr(routes, "SqlAlchemyVisualTraceRepository",
                        lambda _s: Trace(state.world.rows))
    monkeypatch.setattr(routes, "SqlAlchemyGenerationRepository",
                        lambda _s: state.world.generations)
    app.dependency_overrides[current_tenant] = lambda: state.tenant
    app.dependency_overrides[current_principal] = lambda: state.principal
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, codex_bridge_enabled=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        state.client = client
        state.get = lambda session_id=None: client.get(
            URL.format(session_id or state.world.session.id))
        yield state
    for dependency in (current_tenant, current_principal, get_settings):
        app.dependency_overrides.pop(dependency, None)


def test_the_route_answers_the_lengths_with_no_store(api):
    response = api.get()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "owned_test_target": True,
        "has_type_steps": True,
        "type_steps": [
            {"step_index": 1, "locator_name": "Tên đăng nhập", "text_chars": len(NAME)},
            {"step_index": 1, "locator_name": "Mật khẩu", "text_chars": len(PASSWORD)},
        ],
    }


def test_the_route_without_the_flag_answers_an_empty_list(api):
    api.world = World(owned=False)
    response = api.get()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "owned_test_target": False, "has_type_steps": True, "type_steps": []}


def test_the_route_flag_off_and_no_type_step_says_has_type_steps_false(api):
    rows = Rows()
    rows.op("navigate", purpose="setup")
    rows.step(1, rows.op("click", name="Open"))
    api.world = World(rows, owned=False)
    assert api.get().json() == {
        "owned_test_target": False, "has_type_steps": False, "type_steps": []}


def test_the_route_without_type_steps_answers_an_empty_list(api):
    rows = Rows()
    rows.op("navigate", purpose="setup")
    rows.step(1, rows.op("click", name="Open"))
    api.world = World(rows)
    assert api.get().json() == {
        "owned_test_target": True, "has_type_steps": False, "type_steps": []}


def test_the_route_has_the_post_status_and_detail_for_each_refusal(api):
    rows = login_rows()[0]
    api.world = World(rows, session=rows.session(state="running"))
    response = api.get()
    assert (response.status_code, response.json()) == (
        409, {"detail": {"code": "session_not_completed"}})
    rows = login_rows()[0]
    rows.frames.pop()
    api.world = World(rows)
    response = api.get()
    assert (response.status_code, response.json()["detail"]["code"]) == (409, "evidence_expired")


def test_the_route_is_404_the_same_for_no_right_no_tenant_and_no_session(api):
    texts = set()
    api.principal = Principal("viewer-1", {TENANT: frozenset({Role.VIEWER})}, {})
    texts.add(api.get().text)
    api.principal = contributor()
    api.tenant = "tenant-b"
    texts.add(api.get().text)
    api.tenant = TENANT
    texts.add(api.get(uuid4()).text)
    assert texts == {'{"detail":"Visual exploration not found."}'}
    assert api.get().status_code == 200  # the control: the same world is readable by a right one


def test_the_answer_holds_only_lengths_and_names_never_a_value_or_an_id(api):
    response = api.get()
    data = response.json()
    assert set(data) == {"owned_test_target", "has_type_steps", "type_steps"}
    trace = api.world.rows.build()
    for item in data["type_steps"]:
        assert set(item) == {"step_index", "locator_name", "text_chars"}
    forbidden = [str(s.operation_id) for s in trace.steps]
    forbidden += [str(s.locator_id) for s in trace.steps if s.locator_id]
    forbidden += [str(trace.session_id), "ZQ7731", "ZQ9042", "version:", "bbox"]
    assert not [text for text in forbidden if text in response.text]


def test_the_route_logs_nothing_and_writes_nothing(api, caplog):
    with caplog.at_level(logging.DEBUG):
        api.get()
    assert not [r for r in caplog.records if r.name.startswith(("api", "application"))]
    api.world.assert_nothing_written()


def test_the_only_route_added_is_a_get():
    paths = {
        path: set(methods)
        for path, methods in app.openapi()["paths"].items()
        if path.endswith("/test-draft/inputs")
    }
    assert paths == {"/api/v1/vision/explorations/{session_id}/test-draft/inputs": {"get"}}
