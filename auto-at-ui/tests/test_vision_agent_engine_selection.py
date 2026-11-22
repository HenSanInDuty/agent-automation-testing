"""Engine selection (route + application), the agent step log and its migration.

Everything that touches PostgreSQL uses the UUID-named databases of `vision_trace_fixtures`;
nothing here reads application settings or the configured `DATABASE_URL`.
"""

# ruff: noqa: F811  (pytest fixtures imported from test_vision_provider_submission)
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import config
import pytest
from alembic import command
from alembic.config import Config
from api.v1.dependencies.vision import codex_readiness
from application.vision import SubmitVisualExploration, VisionStateError
from domain.codex_bridge import input_fingerprint
from domain.vision import VisualSessionScope
from infrastructure.persistence.models import (
    ProjectExecutionPolicyModel,
    VisualAgentStepModel,
    VisualExplorationSessionModel,
)
from main import app
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.exc import IntegrityError
from test_codex_model_batch import Readiness
from test_vision_provider_submission import counts, submission, submit  # noqa: F401
from vision_trace_fixtures import session_values

pytest_plugins = ["vision_trace_fixtures"]
MIGRATION = "b7c9d1e3f5a7"
PREVIOUS = "a4c6e8f01234"


@pytest.fixture(autouse=True)
def restore_alembic_logger_state():
    # Alembic fileConfig disables existing loggers; do not leak that into later tests.
    before = {name: logger.disabled for name, logger in logging.Logger.manager.loggerDict.items()
              if isinstance(logger, logging.Logger)}
    yield
    for name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            logger.disabled = before.get(name, False)


@pytest.fixture
def bridge(submission):
    """A ready Codex bridge provider with consent, v4 tracing and the agent flag still off."""
    client, payload, set_policy, settings = submission
    settings.vision_trace_v4_enabled = True
    app.dependency_overrides[codex_readiness] = lambda: Readiness()
    policy = set_policy(
        "codex_cli", model="gpt-6-luna", raw_screenshot_transfer_accepted=False,
        raw_screenshot_transfer_provider=None,
        codex={"dom_transfer_accepted": True, "dom_transfer_provider": "codex_cli"},
    )
    payload.update(
        expected_provider="codex_cli", expected_model="gpt-6-luna",
        expected_input_policy_fingerprint=input_fingerprint(policy),
    )
    return client, payload, set_policy, settings


def engine_of(factory, session_id):
    with factory() as db:
        return db.get(VisualExplorationSessionModel, UUID(str(session_id))).exploration_engine


# --- route: selection ------------------------------------------------------------------

@pytest.mark.parametrize("v4", [False, True])
def test_request_without_engine_creates_a_planner_session(submission, trace_database, v4):
    client, payload, _, settings = submission
    factory, *_ = trace_database
    settings.vision_trace_v4_enabled = v4
    assert "engine" not in payload
    response = submit(client, payload)
    assert response.status_code == 202, response.text
    assert response.json()["engine"] == "planner"
    assert engine_of(factory, response.json()["id"]) == "planner"
    explicit = submit(client, payload | {"engine": "planner"}, key="explicit")
    assert explicit.status_code == 202 and explicit.json()["engine"] == "planner"


@pytest.mark.parametrize("engine", ["react", "", "AGENT_LOOP", None, 3])
def test_unknown_engine_is_a_validation_error_and_creates_nothing(
    submission, trace_database, engine,
):
    client, payload, *_ = submission
    factory, *_ = trace_database
    before = counts(factory)
    assert submit(client, payload | {"engine": engine}).status_code == 422
    assert counts(factory) == before


def test_agent_loop_is_refused_while_the_flag_is_off(bridge, trace_database):
    client, payload, _, settings = bridge
    factory, *_ = trace_database
    assert settings.vision_agent_loop_enabled is False
    before = counts(factory)
    response = submit(client, payload | {"engine": "agent_loop"})
    assert response.status_code == 422 and "disabled" in response.json()["detail"]
    assert counts(factory) == before


def test_agent_loop_requires_a_bridge_provider(submission, trace_database):
    client, payload, _, settings = submission  # provider is gemini
    factory, *_ = trace_database
    settings.vision_trace_v4_enabled = True
    settings.vision_agent_loop_enabled = True
    before = counts(factory)
    response = submit(client, payload | {"engine": "agent_loop"})
    assert response.status_code == 422 and "bridge" in response.json()["detail"]
    assert counts(factory) == before
    assert submit(client, payload, key="planner").status_code == 202


@pytest.mark.parametrize("allowed", [[], ["https://unrelated.fixture.test"]])
def test_agent_loop_target_must_be_inside_the_project_allowlist(
    bridge, trace_database, allowed,
):
    client, payload, _, settings = bridge
    factory, scope, *_ = trace_database
    settings.vision_agent_loop_enabled = True
    with factory.begin() as session:
        session.get(ProjectExecutionPolicyModel, scope.project_id).allowed_origins = allowed
    before = counts(factory)
    response = submit(client, payload | {"engine": "agent_loop"})
    assert response.status_code == 422 and "origin" in response.json()["detail"]
    assert counts(factory) == before
    # v4 planner behaviour is unchanged: the worker, not submission, enforces its allowlist.
    assert submit(client, payload, key="planner").status_code == 202


def test_agent_loop_session_is_created_and_read_back_with_its_engine(bridge, trace_database):
    client, payload, _, settings = bridge
    factory, *_ = trace_database
    settings.vision_agent_loop_enabled = True
    response = submit(client, payload | {"engine": "agent_loop"})
    assert response.status_code == 202, response.text
    created = response.json()
    assert created["engine"] == "agent_loop" and created["trace_version"] == "v4"
    assert engine_of(factory, created["id"]) == "agent_loop"
    read = client.get(f"/api/v1/vision/explorations/{created['id']}")
    assert read.status_code == 200 and read.json()["engine"] == "agent_loop"
    # Same key, same request: the stored session is returned; flag state no longer matters.
    settings.vision_agent_loop_enabled = False
    assert submit(client, payload | {"engine": "agent_loop"}).json() == created


def test_idempotency_key_cannot_switch_engine(bridge, trace_database):
    client, payload, _, settings = bridge
    factory, *_ = trace_database
    settings.vision_agent_loop_enabled = True
    first = submit(client, payload | {"engine": "agent_loop"})
    assert first.status_code == 202
    before = counts(factory)
    for engine in ("planner", None):
        body = payload if engine is None else payload | {"engine": engine}
        again = submit(client, body)
        assert again.status_code == 422 and "different exploration" in again.json()["detail"]
    assert counts(factory) == before


def test_session_created_before_the_column_existed_reads_as_planner(
    submission, trace_database,
):
    client, *_ = submission
    _, scope, *_ = trace_database
    read = client.get(f"/api/v1/vision/explorations/{scope.session_id}")
    assert read.status_code == 200, read.text
    assert read.json()["engine"] == "planner"


# --- route: policy flag ----------------------------------------------------------------

def test_policy_read_reports_the_agent_loop_flag(submission):
    client, _, _, settings = submission
    assert client.get("/api/v1/vision/policy").json()["agent_loop_enabled"] is False
    settings.vision_agent_loop_enabled = True
    assert client.get("/api/v1/vision/policy").json()["agent_loop_enabled"] is True


def test_policy_write_tolerates_an_echoed_flag_and_never_applies_it(submission):
    client, _, _, settings = submission
    settings.gemini_api_key = "synthetic-secret"  # an enabled gemini policy must be savable
    current = client.get("/api/v1/vision/policy").json()
    assert current["agent_loop_enabled"] is False
    # The dashboard sends the whole read model back; the server flag is the only authority.
    echoed = client.put("/api/v1/vision/policy", json=current | {"agent_loop_enabled": True})
    assert echoed.status_code == 200, echoed.text
    assert echoed.json()["agent_loop_enabled"] is False
    assert settings.vision_agent_loop_enabled is False
    settings.vision_agent_loop_enabled = True
    assert client.put("/api/v1/vision/policy", json=current).json()["agent_loop_enabled"] is True


# --- route: reload keeps the engine ----------------------------------------------------

def test_reload_keeps_the_engine_of_the_original_session(bridge, trace_database):
    client, payload, _, settings = bridge
    factory, *_ = trace_database
    settings.vision_agent_loop_enabled = True
    original = submit(client, payload | {"engine": "agent_loop"}).json()
    with factory.begin() as db:
        db.get(VisualExplorationSessionModel, UUID(original["id"])).state = "completed"
    confirmation = {key: value for key, value in payload.items() if key.startswith("expected_")}
    reloaded = client.post(
        f"/api/v1/vision/explorations/{original['id']}/reload", json=confirmation,
        headers={"Idempotency-Key": "reload-agent"},
    )
    assert reloaded.status_code == 202, reloaded.text
    assert reloaded.json()["id"] != original["id"] and reloaded.json()["engine"] == "agent_loop"
    assert engine_of(factory, reloaded.json()["id"]) == "agent_loop"


def test_reload_of_a_planner_session_stays_planner_even_with_the_flag_on(bridge, trace_database):
    client, payload, _, settings = bridge
    factory, *_ = trace_database
    original = submit(client, payload).json()
    settings.vision_agent_loop_enabled = True
    with factory.begin() as db:
        db.get(VisualExplorationSessionModel, UUID(original["id"])).state = "completed"
    confirmation = {key: value for key, value in payload.items() if key.startswith("expected_")}
    reloaded = client.post(
        f"/api/v1/vision/explorations/{original['id']}/reload", json=confirmation,
        headers={"Idempotency-Key": "reload-planner"},
    )
    assert reloaded.status_code == 202, reloaded.text
    assert reloaded.json()["engine"] == "planner"


def test_reload_of_an_agent_session_is_refused_after_the_flag_is_turned_off(
    bridge, trace_database,
):
    client, payload, _, settings = bridge
    factory, *_ = trace_database
    settings.vision_agent_loop_enabled = True
    original = submit(client, payload | {"engine": "agent_loop"}).json()
    settings.vision_agent_loop_enabled = False
    with factory.begin() as db:
        db.get(VisualExplorationSessionModel, UUID(original["id"])).state = "completed"
    before = counts(factory)
    confirmation = {key: value for key, value in payload.items() if key.startswith("expected_")}
    refused = client.post(
        f"/api/v1/vision/explorations/{original['id']}/reload", json=confirmation,
        headers={"Idempotency-Key": "reload-off"},
    )
    assert refused.status_code == 422 and "disabled" in refused.json()["detail"]
    assert counts(factory) == before


# --- application: engine rules without a database --------------------------------------

def submitter(provider):
    repository = Mock()
    repository.get_by_key.return_value = None
    catalog = Mock()
    catalog.get_project.return_value = SimpleNamespace(default_target="web_ui")
    runtime = SimpleNamespace(vision=SimpleNamespace(provider=provider, model="fixture"))
    use_case = SubmitVisualExploration(repository, Mock(), catalog, Mock(), Mock(), Mock(), Mock())
    return use_case, runtime, repository


def execute(use_case, runtime, **overrides):
    return use_case.execute(**{
        "tenant_id": "tenant", "project_id": uuid4(), "correlation_id": None,
        "target_url": "https://fixture.test/", "task_intent": "Explore", "idempotency_key": "k",
        "runtime": runtime, "actor": "actor", "intent_encryption_key": None,
        "intent_retention_days": 1, **overrides,
    })


@pytest.mark.parametrize("provider,enabled,engine,message", [
    ("codex_cli", False, "agent_loop", "disabled"),
    ("claude_cli", False, "agent_loop", "disabled"),
    ("huggingface", True, "agent_loop", "bridge"),
    ("codex_cli", True, "bogus", "unknown exploration engine"),
    ("codex_cli", False, "", "unknown exploration engine"),
])
def test_engine_rules_reject_before_any_write(provider, enabled, engine, message):
    use_case, runtime, repository = submitter(provider)
    with pytest.raises(VisionStateError, match=message):
        execute(use_case, runtime, engine=engine, agent_loop_enabled=enabled,
                trace_v4_enabled=True)
    repository.add.assert_not_called()


# --- migration -------------------------------------------------------------------------

def migrate(disposable_database, monkeypatch):
    url = disposable_database.url.render_as_string(hide_password=False)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=url))
    return Config("alembic.ini")


def version(engine):
    with engine.connect() as connection:
        return connection.scalar(text("SELECT version_num FROM alembic_version"))


def test_migration_adds_engine_and_step_table_and_downgrade_removes_only_them(
    disposable_database, monkeypatch,
):
    engine = disposable_database
    alembic = migrate(engine, monkeypatch)
    command.upgrade(alembic, PREVIOUS)
    assert "visual_agent_steps" not in inspect(engine).get_table_names()
    scope = VisualSessionScope("legacy-tenant", uuid4(), uuid4())
    metadata = MetaData()
    projects = Table("projects", metadata, autoload_with=engine)
    sessions = Table("visual_exploration_sessions", metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(projects.insert().values(
            id=scope.project_id, tenant_id=scope.tenant_id, name="Legacy",
            default_target="web_ui",
        ))
        connection.execute(sessions.insert().values(**session_values(scope)))

    command.upgrade(alembic, "head")
    assert version(engine) == MIGRATION
    columns = {c["name"]: c for c in inspect(engine).get_columns("visual_exploration_sessions")}
    assert columns["exploration_engine"]["nullable"] is False
    assert str(columns["exploration_engine"]["type"]) == "VARCHAR(20)"
    with engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT exploration_engine FROM visual_exploration_sessions"
        )) == "planner"
    step_columns = {c["name"]: c for c in inspect(engine).get_columns("visual_agent_steps")}
    assert set(step_columns) == {
        "id", "tenant_id", "project_id", "session_id", "step_index", "snapshot_version",
        "evaluation_previous_goal", "memory", "next_goal", "actions", "operation_ids",
        "stop_reason", "job_id", "created_at",
    }
    assert {name for name, c in step_columns.items() if c["nullable"]} == {"stop_reason", "job_id"}
    assert [u["column_names"] for u in inspect(engine).get_unique_constraints(
        "visual_agent_steps")] == [["session_id", "step_index"]]
    assert inspect(engine).get_foreign_keys("visual_agent_steps")[0]["name"] == (
        "fk_visual_agent_step_session"
    )
    # The bridge job sequence bound is untouched by this revision (K1: ceiling stays 20).
    sequence_checks = [
        check["sqltext"] for check in inspect(engine).get_check_constraints("codex_bridge_jobs")
        if check["name"] == "ck_codex_job_sequence"
    ]
    assert len(sequence_checks) == 1 and "20" in sequence_checks[0]
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(
            "UPDATE visual_exploration_sessions SET exploration_engine = 'bogus'"
        ))
    with engine.begin() as connection:
        connection.execute(text(
            "UPDATE visual_exploration_sessions SET exploration_engine = 'agent_loop'"
        ))

    command.downgrade(alembic, "-1")
    assert version(engine) == PREVIOUS
    assert "visual_agent_steps" not in inspect(engine).get_table_names()
    columns = {c["name"] for c in inspect(engine).get_columns("visual_exploration_sessions")}
    assert "exploration_engine" not in columns and "trace_version" in columns
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM visual_exploration_sessions")) == 1
    command.upgrade(alembic, "head")
    assert version(engine) == MIGRATION


# --- step log --------------------------------------------------------------------------

def step_values(**changes):
    return dict(
        step_index=1, snapshot_version=2, evaluation_previous_goal="Success",
        memory="Seen 1 control", next_goal="Click Continue",
        actions=[{"kind": "click", "ref": "2:1", "result": "completed"}],
        operation_ids=[uuid4()], stop_reason=None, job_id=uuid4(),
    ) | changes


def test_record_agent_step_stores_a_step_and_reads_steps_in_index_order(trace_database):
    _, scope, uow, lease, _ = trace_database
    assert uow.agent_steps(scope) == []
    job_id, operation_id = uuid4(), uuid4()
    saved = uow.record_agent_step(lease, **step_values(
        step_index=2, job_id=job_id, operation_ids=[operation_id],
    ))
    assert saved.step_index == 2 and saved.job_id == job_id and saved.created_at is not None
    uow.record_agent_step(lease, **step_values(
        step_index=1, operation_ids=[], stop_reason="agent_done",
        actions=[{"kind": "back", "skipped_reason": "origin_blocked"}],
    ))
    steps = uow.agent_steps(scope)
    assert [s.step_index for s in steps] == [1, 2]
    assert steps[0].stop_reason == "agent_done" and steps[0].operation_ids == []
    assert steps[1].operation_ids == [str(operation_id)]
    assert steps[1].actions == [{"kind": "click", "ref": "2:1", "result": "completed"}]
    assert (steps[1].tenant_id, steps[1].project_id, steps[1].session_id) == (
        scope.tenant_id, scope.project_id, scope.session_id)


def test_record_agent_step_is_fenced_by_the_session_lease(trace_database):
    factory, scope, uow, lease, _ = trace_database
    with factory.begin() as db:
        db.get(VisualExplorationSessionModel, scope.session_id).fencing_token += 1
    with pytest.raises(ValueError, match="stale or expired"):
        uow.record_agent_step(lease, **step_values())
    assert uow.agent_steps(scope) == []


def test_record_agent_step_is_refused_after_the_lease_expires(trace_database):
    factory, scope, uow, lease, _ = trace_database
    with factory.begin() as db:
        db.get(VisualExplorationSessionModel, scope.session_id).lease_expires_at = (
            datetime.now(UTC) - timedelta(seconds=1)
        )
    with pytest.raises(ValueError, match="stale or expired"):
        uow.record_agent_step(lease, **step_values())


def test_agent_step_index_is_unique_per_session(trace_database):
    _, scope, uow, lease, _ = trace_database
    uow.record_agent_step(lease, **step_values(step_index=1))
    with pytest.raises(IntegrityError):
        uow.record_agent_step(lease, **step_values(step_index=1))
    uow.record_agent_step(lease, **step_values(step_index=2))
    assert [s.step_index for s in uow.agent_steps(scope)] == [1, 2]


def test_agent_step_cannot_claim_more_operations_than_actions(trace_database):
    _, scope, uow, lease, _ = trace_database
    with pytest.raises(ValueError, match="more operations than actions"):
        uow.record_agent_step(lease, **step_values(operation_ids=[uuid4(), uuid4()]))
    assert uow.agent_steps(scope) == []


def test_agent_step_content_is_redacted_before_it_is_stored(trace_database):
    factory, scope, uow, lease, _ = trace_database
    uow.record_agent_step(lease, **step_values(
        evaluation_previous_goal="Login failed: password=hunter2",
        memory="cookie=abc123; kept the page title",
        next_goal="Retry with api_key=sk-live-999",
        actions=[{"kind": "type", "ref": "2:3", "text": "token=s3cr3t-value",
                  "expected_outcome": "see https://fixture.test/?session=zzz", "password": "x"}],
    ))
    with factory() as db:
        row = db.scalar(select(VisualAgentStepModel))
        stored = " ".join([
            row.evaluation_previous_goal, row.memory, row.next_goal, str(row.actions),
        ])
    for secret in ("hunter2", "abc123", "sk-live-999", "s3cr3t-value", "zzz"):
        assert secret not in stored
    assert "[REDACTED]" in stored and "kept the page title" in stored
    assert row.actions[0]["kind"] == "type" and row.actions[0]["ref"] == "2:3"


def test_another_tenant_or_project_cannot_read_agent_steps(trace_database):
    _, scope, uow, lease, _ = trace_database
    uow.record_agent_step(lease, **step_values())
    assert len(uow.agent_steps(scope)) == 1
    assert uow.agent_steps(VisualSessionScope("tenant-b", scope.project_id, scope.session_id)) == []
    assert uow.agent_steps(VisualSessionScope(scope.tenant_id, uuid4(), scope.session_id)) == []
    assert uow.agent_steps(VisualSessionScope(scope.tenant_id, scope.project_id, uuid4())) == []


def test_database_rejects_a_step_whose_scope_does_not_match_its_session(trace_database):
    factory, scope, *_ = trace_database
    with pytest.raises(IntegrityError), factory.begin() as db:
        db.add(VisualAgentStepModel(
            tenant_id="tenant-b", project_id=scope.project_id, session_id=scope.session_id,
            step_index=1, snapshot_version=1, evaluation_previous_goal="x", memory="",
            next_goal="y", actions=[], operation_ids=[],
        ))


def test_database_check_limits_the_exploration_engine(trace_database):
    factory, scope, *_ = trace_database
    with factory.begin() as db:
        assert db.get(VisualExplorationSessionModel, scope.session_id).exploration_engine == (
            "planner")
        db.get(VisualExplorationSessionModel, scope.session_id).exploration_engine = "agent_loop"
    with pytest.raises(IntegrityError), factory.begin() as db:
        db.get(VisualExplorationSessionModel, scope.session_id).exploration_engine = "react"
