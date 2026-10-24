"""Upgrade only UUID-named databases owned by the isolated fixture."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import config
import pytest
from alembic import command
from alembic.config import Config
from domain.vision import VisualSessionScope
from infrastructure.persistence.models import CodexBridgeJobModel, VisualExplorationSessionModel
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from test_codex_bridge_contracts import NOW, request
from vision_trace_fixtures import session_values

pytest_plugins = ["vision_trace_fixtures"]


@pytest.fixture(autouse=True)
def restore_alembic_logger_state():
    # Alembic fileConfig disables existing loggers; do not leak that into later tests.
    before = {name: logger.disabled for name, logger in logging.Logger.manager.loggerDict.items()
              if isinstance(logger, logging.Logger)}
    yield
    for name, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger):
            logger.disabled = before.get(name, False)


def test_upgrade_preserves_null_consent_and_enforces_scope_identity_and_terminal_state(
    disposable_database, monkeypatch,
):
    engine = disposable_database
    url = engine.url.render_as_string(hide_password=False)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=url))
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "f9a0b1c2d3e4")
    scope = VisualSessionScope("fixture", uuid4(), uuid4())
    metadata = MetaData()
    projects = Table("projects", metadata, autoload_with=engine)
    sessions = Table("visual_exploration_sessions", metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(projects.insert().values(
            id=scope.project_id, tenant_id=scope.tenant_id, name="Fixture", default_target="web_ui",
        ))
        connection.execute(sessions.insert().values(**session_values(scope)))
    command.upgrade(alembic, "head")
    with Session(engine) as session:
        legacy = session.get(VisualExplorationSessionModel, scope.session_id)
        assert legacy.model_input_policy is None and legacy.provider == "fixture"
        assert session.scalar(select(CodexBridgeJobModel)) is None
    columns = {c["name"] for c in inspect(engine).get_columns("codex_bridge_jobs")}
    assert not columns & {"dom", "image", "prompt", "output", "auth", "payload"}
    req = request(
        tenant_id=scope.tenant_id, project_id=scope.project_id, session_id=scope.session_id,
    )
    values = {key: getattr(req, key) for key in (
        "job_id", "bridge_id", "tenant_id", "project_id", "session_id", "correlation_id",
        "fencing_token", "request_sequence", "observation_id", "snapshot_id", "state_fingerprint",
        "stage", "deadline", "created_at",
    )} | {"request_hash": "a" * 64, "updated_at": NOW, "status": "queued"}
    jobs = CodexBridgeJobModel.__table__
    with engine.begin() as connection:
        connection.execute(jobs.insert().values(**values))
    for changes in ({"tenant_id": "wrong"}, {"project_id": uuid4()}, {}):
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(jobs.insert().values(**(values | changes | {"job_id": uuid4()})))
    with pytest.raises(ProgrammingError, match="immutable"), engine.begin() as connection:
        connection.execute(jobs.update().values(tenant_id="wrong"))
    with pytest.raises(ProgrammingError, match="immutable"), engine.begin() as connection:
        connection.execute(text("UPDATE visual_exploration_sessions SET model_input_policy='{}'"))
    with pytest.raises(ProgrammingError, match="transition"), engine.begin() as connection:
        connection.execute(jobs.update().values(status="completed"))
    for state in ("claimed", "running", "completed"):
        with engine.begin() as connection:
            connection.execute(jobs.update().values(
                status=state, updated_at=NOW + timedelta(seconds=1),
            ))
    with pytest.raises(ProgrammingError, match="transition"), engine.begin() as connection:
        connection.execute(jobs.update().values(status="running"))
    with pytest.raises(ProgrammingError, match="transition"), engine.begin() as connection:
        connection.execute(jobs.update().values(response_hash="b" * 64))
