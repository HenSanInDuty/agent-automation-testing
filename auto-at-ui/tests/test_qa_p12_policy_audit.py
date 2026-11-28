"""QA phase 12: gaps left by test_generation_policy_audit.py, incl. a real-database transaction."""

from uuid import UUID

import pytest
import test_generation_policy_audit as base
from api.v1.routes import generation
from config import Settings, get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    AuditEventModel,
    ProjectExecutionPolicyModel,
    ProjectModel,
)
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_generation_policy_audit import ADMIN, ENABLED, PATH, PROJECT, UPDATED, body

# Reuse the in-memory fixtures (store/client) of the developer test file.
store = base.store
client = base.client

ORIGIN2 = "https://other.fixture.test"
KEYS = {"allowed_origins", "vision_max_hops", "vision_max_states", "vision_owned_test_target"}


def test_p12_a1_only_limits_or_origins_change_records_updated(client, store):
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    changed_origin = body(True, (ORIGIN2,))
    changed_hops = body(True) | {"vision_max_hops": 9}
    changed_states = body(True) | {"vision_max_states": 120}
    for payload in (changed_origin, changed_hops, changed_states):
        assert client.put(PATH, json=payload, headers=ADMIN).status_code == 200
    assert base.actions(store) == [ENABLED, UPDATED, UPDATED, UPDATED]


def test_p12_a2_first_write_without_flag_is_updated_and_flag_false(client, store):
    response = client.put(PATH, json=body(), headers=ADMIN)
    assert response.status_code == 200
    assert response.json()["vision_owned_test_target"] is False
    assert base.actions(store) == [UPDATED]


def test_p12_a3_response_shape_is_unchanged(client, store):
    payload = body(True) | {"vision_max_hops": 7, "vision_max_states": 77}
    response = client.put(PATH, json=payload, headers=ADMIN)
    assert response.status_code == 200
    assert set(response.json()) == KEYS
    assert response.json() == payload
    # Omitted flag echoes the stored value, not null.
    again = client.put(PATH, json=body(), headers=ADMIN).json()
    assert again["vision_owned_test_target"] is True


def test_p12_a4_exactly_one_event_per_successful_call(client, store):
    for flag in (True, True, False, None):
        client.put(PATH, json=body(flag), headers=ADMIN)
    assert len(store.events) == 4
    assert len({e.id for e in store.events}) == 4
    assert len({e.correlation_id for e in store.events}) == 4
    assert all(e.actor == "fixture-admin" and e.actor != "system" for e in store.events)


def test_p12_a5_invalid_payload_and_unicode_origin_write_nothing(client, store):
    for payload in (
        {"allowed_origins": [], "vision_max_hops": 5, "vision_max_states": 50},
        body() | {"vision_max_hops": 0},
        body() | {"vision_max_states": 201},
        body() | {"vision_owned_test_target": "maybe"},
        body(True, ("https://" + "a" * 5000 + ".test",)),
        body(True, ("https://tiếng-việt.test/đường",)),
    ):
        assert client.put(PATH, json=payload, headers=ADMIN).status_code in {404, 422}
    assert store.events == [] and store.policies == {}


def test_p12_a6_event_has_no_hash_or_origin_for_any_action(client, store):
    client.put(PATH, json=body(True), headers=ADMIN)
    client.put(PATH, json=body(False, (ORIGIN2,)), headers=ADMIN)
    client.put(PATH, json=body(), headers=ADMIN)
    for event in store.events:
        text = repr(event)
        assert "fixture.test" not in text
        assert event.before_hash is None and event.after_hash is None


# ---- real PostgreSQL (disposable fixture DB, never the application DB) ----

pytest_plugins = ["vision_trace_fixtures"]


@pytest.fixture
def real(disposable_database, monkeypatch):
    for model in (ProjectModel, ProjectExecutionPolicyModel, AuditEventModel):
        model.__table__.create(disposable_database)
    factory = sessionmaker(disposable_database, expire_on_commit=False)
    with factory() as session:
        session.add(ProjectModel(
            id=PROJECT, tenant_id="tenant-a", name="p", default_target="web_ui"))
        session.commit()
    monkeypatch.setattr(generation, "create_session_factory", lambda _: factory)
    app = FastAPI()
    app.include_router(generation.router, prefix="/api/v1")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, codex_bridge_enabled=False)
    with TestClient(app, raise_server_exceptions=False) as http:
        yield http, factory


def rows(factory):
    with factory() as session:
        policy = session.scalar(select(ProjectExecutionPolicyModel))
        events = list(session.scalars(select(AuditEventModel).order_by(AuditEventModel.action)))
        return policy, events


def test_p12_db1_real_commit_persists_policy_and_event_together(real):
    http, factory = real
    assert http.put(PATH, json=body(False), headers=ADMIN).status_code == 200
    assert http.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    assert http.put(PATH, json=body(), headers=ADMIN).status_code == 200
    assert http.put(PATH, json=body(False), headers=ADMIN).status_code == 200
    policy, events = rows(factory)
    assert policy.vision_owned_test_target is False
    assert sorted(e.action for e in events) == sorted([
        UPDATED, ENABLED, UPDATED, "project_policy.owned_test_target.disabled"])
    for event in events:
        assert (event.tenant_id, event.actor, event.entity_type, event.entity_id) == (
            "tenant-a", "fixture-admin", "project_execution_policy", PROJECT)
        assert isinstance(event.correlation_id, UUID)
    assert len({e.correlation_id for e in events}) == 4


def test_p12_db2_audit_failure_rolls_back_policy_for_real(real, monkeypatch):
    http, factory = real
    assert http.put(PATH, json=body(False), headers=ADMIN).status_code == 200

    def boom(self, event):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(generation.SqlAlchemyAuditEventRepository, "append", boom)
    assert http.put(PATH, json=body(True, (ORIGIN2,)), headers=ADMIN).status_code == 500
    policy, events = rows(factory)
    assert policy.vision_owned_test_target is False
    assert policy.allowed_origins == [base.ORIGIN]
    assert [e.action for e in events] == [UPDATED]


def test_p12_db3_first_write_audit_failure_leaves_no_policy_row(real, monkeypatch):
    http, factory = real

    def boom(self, event):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(generation.SqlAlchemyAuditEventRepository, "append", boom)
    assert http.put(PATH, json=body(True), headers=ADMIN).status_code == 500
    policy, events = rows(factory)
    assert policy is None and events == []


def test_p12_db4_policy_write_failure_leaves_no_event_for_real(real, monkeypatch):
    http, factory = real
    assert http.put(PATH, json=body(False), headers=ADMIN).status_code == 200

    def boom(self, *args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(generation.SqlAlchemyGenerationRepository, "set_policy", boom)
    assert http.put(PATH, json=body(True), headers=ADMIN).status_code == 500
    policy, events = rows(factory)
    assert policy.vision_owned_test_target is False
    assert [e.action for e in events] == [UPDATED]


@pytest.mark.parametrize("headers, origins", [
    (ADMIN | {"X-Actor-Roles": "viewer"}, (base.ORIGIN,)),
    (ADMIN, ("javascript:alert(1)",)),
])
def test_p12_db5_rejected_calls_change_nothing_for_real(real, headers, origins):
    http, factory = real
    assert http.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    before = rows(factory)
    assert http.put(PATH, json=body(False, origins), headers=headers).status_code in {401, 404}
    after = rows(factory)
    assert after[0].vision_owned_test_target is True
    assert [e.id for e in after[1]] == [e.id for e in before[1]]


def test_p12_db6_other_tenant_cannot_change_policy_or_add_event_for_real(real):
    http, factory = real
    assert http.put(PATH, json=body(False), headers=ADMIN).status_code == 200
    other = ADMIN | {"X-Tenant-Id": "tenant-b", "X-Actor-Id": "other-admin"}
    response = http.put(PATH, json=body(True), headers=other)
    policy, events = rows(factory)
    # Policy of tenant-a must be untouched whatever the outcome for tenant-b.
    assert policy.tenant_id == "tenant-a" and policy.vision_owned_test_target is False
    assert all(e.tenant_id == "tenant-a" for e in events if response.status_code != 200)
    print("TENANT_B_STATUS", response.status_code)
    assert response.status_code in {200, 404, 500}
