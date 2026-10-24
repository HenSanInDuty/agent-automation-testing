"""Real policy transactions against a disposable database, never the application DB."""

from uuid import UUID

import pytest
from api.v1.dependencies import authorization, vision
from application.authentication import AccountService
from application.vision_policy import VISION_POLICY_AUDIT_PREFIX
from config import get_settings
from fastapi.testclient import TestClient
from infrastructure.persistence.models import AuditEventModel, ConfigurationModel
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
)
from main import app
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_vision_policy import settings
from test_vision_policy_routes import policy_payload

pytest_plugins = ["vision_trace_fixtures"]


@pytest.fixture
def policy_database(disposable_database, monkeypatch):
    ConfigurationModel.__table__.create(disposable_database)
    AuditEventModel.__table__.create(disposable_database)
    factory = sessionmaker(disposable_database, expire_on_commit=False)
    runtime_settings = settings(gemini_api_key="synthetic-secret")
    # Use real dependency composition and repositories with only the connection replaced.
    monkeypatch.setattr(vision, "create_session_factory", lambda _: factory)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_settings] = lambda: runtime_settings
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_http_success_commits_policy_snapshot_and_audit_before_response(policy_database):
    client, factory = policy_database
    response = client.put("/api/v1/vision/policy", json=policy_payload(), headers={
        "X-Tenant-Id": "tenant-a", "X-Actor-Id": "fixture-admin",
    })
    assert response.status_code == 200
    saved_policy = {k: v for k, v in response.json().items() if k != "input_policy_fingerprint"}
    with factory() as session:
        event, = session.scalars(select(AuditEventModel)).all()
        configs = SqlAlchemyConfigurationRepository(session)
        assert configs.get("tenant-a", "agent.runtime.v1")["vision"] == saved_policy
        snapshot = configs.get("tenant-a", VISION_POLICY_AUDIT_PREFIX + str(event.entity_id))
        assert snapshot["before"]["enabled"] is False
        assert snapshot["after"] == saved_policy
        assert event.tenant_id == snapshot["tenant_id"] == "tenant-a"
        assert event.actor == snapshot["actor"] == "fixture-admin"
        assert event.correlation_id == UUID(response.headers["X-Correlation-Id"])
        assert snapshot["correlation_id"] == str(event.correlation_id)
        assert configs.get("tenant-b", "agent.runtime.v1") is None
        assert configs.get("tenant-b", VISION_POLICY_AUDIT_PREFIX + str(event.entity_id)) is None
        assert "synthetic-secret" not in str(snapshot)


@pytest.mark.parametrize("failure_point", ["snapshot", "audit", "commit"])
def test_http_failure_rolls_back_all_writes_and_never_returns_success(
    policy_database, monkeypatch, failure_point,
):
    client, factory = policy_database
    original = {"model": "custom/text", "vision": {"enabled": False}}
    with factory.begin() as session:
        SqlAlchemyConfigurationRepository(session).set("tenant-a", "agent.runtime.v1", original)

    if failure_point == "snapshot":
        real_set = SqlAlchemyConfigurationRepository.set

        def fail_snapshot(self, tenant_id, key, value):
            real_set(self, tenant_id, key, value)
            if key.startswith(VISION_POLICY_AUDIT_PREFIX):
                raise RuntimeError("synthetic snapshot failure")

        monkeypatch.setattr(SqlAlchemyConfigurationRepository, "set", fail_snapshot)
    elif failure_point == "audit":
        real_append = SqlAlchemyAuditEventRepository.append

        def fail_audit(self, event):
            real_append(self, event)
            raise RuntimeError("synthetic audit failure")

        monkeypatch.setattr(SqlAlchemyAuditEventRepository, "append", fail_audit)
    else:
        def fail_commit(self):
            raise RuntimeError("synthetic commit failure")

        monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.put("/api/v1/vision/policy", json=policy_payload(), headers={
        "X-Tenant-Id": "tenant-a",
    })
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    with factory() as session:
        record, = session.scalars(select(ConfigurationModel)).all()
        assert record.key == "agent.runtime.v1"
        assert record.value == original
        assert session.scalars(select(AuditEventModel)).all() == []


def test_matching_csrf_cookie_must_also_validate_against_session(policy_database, monkeypatch):
    client, factory = policy_database
    monkeypatch.setattr(authorization, "create_session_factory", lambda _: factory)
    calls = []

    def invalid_session_csrf(self, token, csrf):
        calls.append((token, csrf))
        return False

    monkeypatch.setattr(AccountService, "csrf_is_valid", invalid_session_csrf)
    client.cookies.set("auto_at_session", "synthetic-session")
    client.cookies.set("auto_at_csrf", "synthetic-csrf")
    response = client.put("/api/v1/vision/policy", json=policy_payload(), headers={
        "X-Tenant-Id": "tenant-a", "X-CSRF-Token": "synthetic-csrf",
    })
    assert response.status_code == 403
    assert calls == [("synthetic-session", "synthetic-csrf")]
    with factory() as session:
        assert session.scalars(select(ConfigurationModel)).all() == []
        assert session.scalars(select(AuditEventModel)).all() == []
