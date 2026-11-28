"""HTTP audit trail for PUT project policy (ADR-047): synthetic fixtures, no database."""

from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from api.v1.routes import generation
from config import Settings, get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient

ORIGIN = "https://fixture.test"
PROJECT = uuid4()
PATH = f"/api/v1/test-generations/projects/{PROJECT}/policy"
ADMIN = {"X-Tenant-Id": "tenant-a", "X-Actor-Id": "fixture-admin",
         "X-Actor-Roles": "project_admin"}
ENABLED = "project_policy.owned_test_target.enabled"
DISABLED = "project_policy.owned_test_target.disabled"
UPDATED = "project_policy.updated"


class Store:
    """Committed state. A route transaction stages writes on a Unit and publishes on success."""

    def __init__(self):
        self.policies = {}
        self.events = []
        self.fail_set = False
        self.fail_append = False


class Unit:
    def __init__(self, store):
        self.store = store
        self.policies = dict(store.policies)
        self.events = []


class Repository:
    def __init__(self, unit):
        self.unit = unit

    def get_policy(self, tenant, project):
        return self.unit.policies.get((tenant, project))

    def set_policy(self, tenant, project, origins, *, vision_owned_test_target=None, **limits):
        if self.unit.store.fail_set:
            raise RuntimeError("database unavailable")
        previous = self.get_policy(tenant, project)
        if vision_owned_test_target is None:
            owned = False if previous is None else previous.vision_owned_test_target
        else:
            owned = vision_owned_test_target
        self.unit.policies[tenant, project] = SimpleNamespace(
            allowed_origins=origins, vision_owned_test_target=owned, **limits)
        return owned


class AuditRepository:
    def __init__(self, unit):
        self.unit = unit

    def append(self, event):
        if self.unit.store.fail_append:
            raise RuntimeError("audit unavailable")
        self.unit.events.append(event)


@contextmanager
def fake_transaction(store):
    unit = Unit(store)
    # An exception raised in the body skips the publish lines below: the rollback.
    yield unit
    store.policies = unit.policies
    store.events.extend(unit.events)


@pytest.fixture
def store(monkeypatch):
    state = Store()
    monkeypatch.setattr(generation, "SqlAlchemyGenerationRepository", Repository)
    monkeypatch.setattr(generation, "SqlAlchemyAuditEventRepository", AuditRepository)
    monkeypatch.setattr(generation, "create_session_factory",
                        lambda _: lambda: nullcontext(Unit(state)))
    monkeypatch.setattr(generation, "transactional_session",
                        lambda _factory: fake_transaction(state))
    return state


@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(generation.router, prefix="/api/v1")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, codex_bridge_enabled=False,
    )
    # Server errors are returned as 500 responses so the tests can assert on the outcome.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def body(flag=None, origins=(ORIGIN,)):
    payload = {"allowed_origins": list(origins), "vision_max_hops": 5, "vision_max_states": 50}
    if flag is not None:
        payload["vision_owned_test_target"] = flag
    return payload


def actions(store):
    return [event.action for event in store.events]


def test_flag_turning_on_records_enabled_event(client, store):
    assert client.put(PATH, json=body(False), headers=ADMIN).status_code == 200
    assert actions(store) == [UPDATED]
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    assert actions(store) == [UPDATED, ENABLED]


def test_flag_turning_off_records_disabled_event(client, store):
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    assert client.put(PATH, json=body(False), headers=ADMIN).status_code == 200
    assert actions(store) == [ENABLED, DISABLED]


def test_first_write_with_flag_on_records_enabled_event(client, store):
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    assert actions(store) == [ENABLED]


def test_omitted_or_unchanged_flag_records_updated_event(client, store):
    assert client.put(PATH, json=body(), headers=ADMIN).status_code == 200
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    # Omitting the flag keeps the stored value (ADR-046), so the state does not change.
    assert client.put(PATH, json=body(), headers=ADMIN).status_code == 200
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    assert actions(store) == [UPDATED, ENABLED, UPDATED, UPDATED]
    assert store.policies[("tenant-a", PROJECT)].vision_owned_test_target is True


def test_audit_event_identifies_actor_tenant_and_project_without_sensitive_values(client, store):
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    event, = store.events
    assert event.actor == "fixture-admin"
    assert event.tenant_id == "tenant-a"
    assert event.entity_type == "project_execution_policy"
    assert event.entity_id == PROJECT
    assert isinstance(event.correlation_id, UUID) and event.correlation_id.version == 4
    assert event.before_hash is None and event.after_hash is None
    assert ORIGIN not in repr(event)


def test_each_request_gets_its_own_correlation_id(client, store):
    client.put(PATH, json=body(True), headers=ADMIN)
    client.put(PATH, json=body(True), headers=ADMIN)
    first, second = store.events
    assert first.correlation_id != second.correlation_id


def test_events_and_policy_state_are_tenant_scoped(client, store):
    assert client.put(PATH, json=body(False), headers=ADMIN).status_code == 200
    other = ADMIN | {"X-Tenant-Id": "tenant-b", "X-Actor-Id": "other-admin"}
    assert client.put(PATH, json=body(True), headers=other).status_code == 200
    assert [(e.tenant_id, e.actor, e.action) for e in store.events] == [
        ("tenant-a", "fixture-admin", UPDATED),
        ("tenant-b", "other-admin", ENABLED),
    ]
    assert store.policies[("tenant-a", PROJECT)].vision_owned_test_target is False


@pytest.mark.parametrize("headers, origins", [
    (ADMIN | {"X-Actor-Roles": "contributor"}, (ORIGIN,)),
    (ADMIN | {"X-Actor-Roles": "viewer"}, (ORIGIN,)),
    ({"X-Actor-Id": "fixture-admin"}, (ORIGIN,)),
    (ADMIN, ("javascript:alert(1)",)),
    (ADMIN, ("https://fixture.test/path",)),
])
def test_rejected_calls_write_no_event_and_keep_policy(client, store, headers, origins):
    assert client.put(PATH, json=body(True), headers=ADMIN).status_code == 200
    policies_before, events_before = dict(store.policies), list(store.events)
    response = client.put(PATH, json=body(False, origins), headers=headers)
    assert response.status_code in {401, 404}
    assert store.policies == policies_before
    assert store.events == events_before


def test_failed_policy_write_leaves_no_event(client, store):
    store.fail_set = True
    response = client.put(PATH, json=body(True), headers=ADMIN)
    assert response.status_code == 500
    assert store.events == [] and store.policies == {}


def test_failed_audit_write_rolls_back_the_policy_change(client, store):
    store.fail_append = True
    response = client.put(PATH, json=body(True), headers=ADMIN)
    assert response.status_code == 500
    assert store.events == [] and store.policies == {}
