"""Additive upgrade and new-writer rollback preserve legacy and v4 evidence."""

from uuid import uuid4

from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import vision
from config import Settings, get_settings
from cryptography.fernet import Fernet
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    ProjectExecutionPolicyModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.repositories import SqlAlchemyVisualTraceRepository
from main import app
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_vision_handoff_repository import (
    test_additive_migration_preserves_legacy_rows_and_defaults as upgrade_legacy,
)
from vision_trace_fixtures import complete_operation, operation

pytest_plugins = ["vision_trace_fixtures"]


def test_upgraded_legacy_session_is_readable_without_invented_operations(
    disposable_database, monkeypatch
):
    from domain.vision import VisualSessionScope

    upgrade_legacy(disposable_database, monkeypatch)
    with Session(disposable_database) as session:
        record = session.scalar(select(VisualExplorationSessionModel))
        scope = VisualSessionScope(record.tenant_id, record.project_id, record.id)
        snapshot = SqlAlchemyVisualTraceRepository(session).snapshot(scope)
        assert all(not snapshot[key] for key in ("operations", "frames", "locators", "handoffs"))


def test_api_writer_gate_and_rollback_leave_existing_versions_and_tombstones(
    trace_database, monkeypatch
):
    factory, scope, uow, lease, _ = trace_database
    root = complete_operation(uow, lease, operation(scope))
    with factory.begin() as session:
        session.add(ProjectExecutionPolicyModel(
            project_id=scope.project_id, tenant_id=scope.tenant_id,
            allowed_origins=["https://fixture.test"], vision_max_hops=2, vision_max_states=5,
        ))
        SqlAlchemyVisualTraceRepository(session).tombstone_frame(scope, root.actual_before_frame_id)
    before = uow.read_snapshot(scope)
    settings = Settings(
        _env_file=None, vision_enabled=True, vision_raw_screenshot_transfer_accepted=True,
        vision_intent_encryption_key=Fernet.generate_key().decode(),
    )
    assert settings.vision_trace_v4_enabled is False
    principal = Principal("admin", {scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {})
    monkeypatch.setattr(vision, "create_session_factory", lambda _: factory)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        current_tenant: lambda: scope.tenant_id, current_principal: lambda: principal,
        get_settings: lambda: settings,
    })
    payload = dict(project_id=str(scope.project_id), target_url="https://fixture.test/",
                   task_intent="Observe synthetic links", use_vision=True)
    try:
        with TestClient(app) as client:
            key = uuid4().hex
            settings.vision_trace_v4_enabled = True
            created = client.post("/api/v1/vision/explorations", json=payload,
                                  headers={"Idempotency-Key": key})
            assert created.status_code == 202, created.text
            assert created.json()["trace_version"] == "v4"
            settings.vision_trace_v4_enabled = False
            repeated = client.post("/api/v1/vision/explorations", json=payload,
                                   headers={"Idempotency-Key": key})
            assert repeated.status_code == 202 and repeated.json() == created.json()
            legacy = client.post("/api/v1/vision/explorations", json=payload,
                                 headers={"Idempotency-Key": uuid4().hex})
            assert legacy.status_code == 202 and legacy.json()["trace_version"] == "legacy"
        assert uow.read_snapshot(scope) == before
        assert before["frames"][0].metadata.deleted_at is not None
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
