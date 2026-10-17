"""Submission confirmation and idempotency against isolated PostgreSQL, via HTTP."""

from uuid import UUID, uuid4

import pytest
from agents.prompts.vision import VISION_PROMPT_VERSION
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, VisionPolicy
from api.v1.dependencies.authorization import current_principal, current_tenant
from api.v1.routes import vision as routes
from config import Settings, get_settings
from domain.authorization import Principal, Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    OutboxEventModel,
    ProjectExecutionPolicyModel,
    VisualExplorationSessionModel,
)
from infrastructure.persistence.repositories import SqlAlchemyConfigurationRepository
from infrastructure.persistence.vision_unit_of_work import SqlAlchemyVisionPolicyReader
from main import app
from sqlalchemy import func, select

pytest_plugins = ["vision_trace_fixtures"]


@pytest.fixture
def submission(trace_database, monkeypatch):
    factory, scope, _, _, _ = trace_database
    settings = Settings(
        _env_file=None, vision_intent_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    with factory.begin() as session:
        session.add(ProjectExecutionPolicyModel(
            tenant_id=scope.tenant_id, project_id=scope.project_id,
            allowed_origins=["https://fixture.test"], vision_max_hops=2, vision_max_states=5,
        ))

    def policy(provider="gemini", **changes):
        value = VisionPolicy(**{
            "enabled": True, "provider": provider,
            "model": "gemini-3.8-flash" if provider == "gemini" else "fixture-hf",
            "raw_screenshot_transfer_accepted": True,
            "raw_screenshot_transfer_provider": provider, **changes,
        })
        with factory.begin() as session:
            SqlAlchemyConfigurationRepository(session).set(
                scope.tenant_id, AGENT_RUNTIME_CONFIG_KEY, {"vision": value.model_dump()},
            )
        return value

    policy()
    monkeypatch.setattr(routes, "create_session_factory", lambda _: factory)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        current_tenant: lambda: scope.tenant_id,
        current_principal: lambda: Principal(
            "fixture-admin", {scope.tenant_id: frozenset({Role.TENANT_ADMIN})}, {},
        ),
        get_settings: lambda: settings,
    })
    payload = dict(
        project_id=str(scope.project_id), correlation_id=str(uuid4()),
        target_url="https://fixture.test/", task_intent="Explore synthetic controls",
        use_vision=True, expected_provider="gemini", expected_model="gemini-3.8-flash",
    )
    try:
        with TestClient(app) as client:
            yield client, payload, policy, settings
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def submit(client, payload, key="fixture-key"):
    return client.post(
        "/api/v1/vision/explorations", json=payload, headers={"Idempotency-Key": key},
    )


def counts(factory):
    with factory() as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (
            VisualExplorationSessionModel, OutboxEventModel,
        ))


@pytest.mark.parametrize("v4", [False, True])
def test_snapshot_and_retry_survive_policy_switch_and_revocation(submission, trace_database, v4):
    client, payload, policy, settings = submission
    factory, scope, _, _, _ = trace_database
    settings.vision_trace_v4_enabled = v4
    response = submit(client, payload)
    assert response.status_code == 202, response.text
    saved = response.json()
    assert saved["provider"] == "gemini" and saved["model"] == "gemini-3.8-flash"
    assert saved["trace_version"] == ("v4" if v4 else "legacy")
    with factory() as session:
        record = session.get(VisualExplorationSessionModel, UUID(saved["id"]))
        assert record.prompt_version == VISION_PROMPT_VERSION
        historical = session.get(VisualExplorationSessionModel, scope.session_id)
        assert historical.prompt_version == "fixture"
    before = counts(factory)
    policy("huggingface", enabled=False, raw_screenshot_transfer_accepted=False)
    settings.vision_trace_v4_enabled = not v4
    with factory.begin() as session:
        session.get(ProjectExecutionPolicyModel, scope.project_id).allowed_origins = []
    assert submit(client, payload).json() == saved
    assert counts(factory) == before
    changed_confirmation = payload | {
        "expected_provider": "huggingface", "expected_model": "fixture-hf",
    }
    response = submit(client, changed_confirmation)
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "vision_policy_changed"}
    assert counts(factory) == before


@pytest.mark.parametrize("change", [
    {"expected_provider": "huggingface", "expected_model": "fixture-hf"},
    {"expected_model": "different-model"},
])
def test_stale_confirmation_never_writes(submission, trace_database, change):
    client, payload, _, _ = submission
    before = counts(trace_database[0])
    response = submit(client, payload | change)
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "vision_policy_changed"}
    assert counts(trace_database[0]) == before


@pytest.mark.parametrize("omit", [
    ("expected_provider",), ("expected_model",), ("expected_provider", "expected_model"),
])
def test_gemini_requires_a_complete_confirmation(submission, trace_database, omit):
    client, payload, _, _ = submission
    before = counts(trace_database[0])
    assert submit(client, {k: v for k, v in payload.items() if k not in omit}).status_code == 422
    assert counts(trace_database[0]) == before


def test_old_hf_client_can_submit_and_retry_after_switch(submission, trace_database):
    client, payload, policy, _ = submission
    policy("huggingface")
    payload.pop("expected_provider")
    payload.pop("expected_model")
    response = submit(client, payload)
    assert response.status_code == 202
    policy()
    before = counts(trace_database[0])
    assert submit(client, payload).json() == response.json()
    assert counts(trace_database[0]) == before


@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
def test_omitted_correlation_reuses_original_generated_identity(
    submission, trace_database, provider,
):
    client, payload, policy, _ = submission
    value = policy(provider)
    payload.update(expected_provider=value.provider, expected_model=value.model)
    payload.pop("correlation_id")
    response = submit(client, payload)
    assert response.status_code == 202
    before = counts(trace_database[0])
    assert submit(client, payload).json() == response.json()
    assert counts(trace_database[0]) == before


@pytest.mark.parametrize("field,value", [
    ("correlation_id", str(uuid4())), ("project_id", str(uuid4())),
    ("task_intent", "Different synthetic intent"), ("target_url", "https://fixture.test/other"),
])
def test_key_cannot_alias_different_identity(submission, trace_database, field, value):
    client, payload, _, _ = submission
    assert submit(client, payload).status_code == 202
    before = counts(trace_database[0])
    assert submit(client, payload | {field: value}).status_code == 422
    assert counts(trace_database[0]) == before


@pytest.mark.parametrize("caller", ["foreign_tenant", "viewer", "csrf"])
def test_retries_do_not_bypass_authorization(submission, trace_database, caller):
    client, payload, _, _ = submission
    assert submit(client, payload).status_code == 202
    before = counts(trace_database[0])
    _, scope, _, _, _ = trace_database
    if caller == "foreign_tenant":
        app.dependency_overrides[current_tenant] = lambda: "foreign"
    elif caller == "viewer":
        app.dependency_overrides[current_principal] = lambda: Principal(
            "reader", {scope.tenant_id: frozenset({Role.VIEWER})}, {},
        )
    else:
        client.cookies.set("auto_at_session", "fixture-session")
        client.cookies.set("auto_at_csrf", "fixture-csrf")
    assert submit(client, payload).status_code in {403, 404}
    assert counts(trace_database[0]) == before


def test_legacy_policy_reader_observes_commits_without_cached_orm_state(submission, trace_database):
    _, _, policy, _ = submission
    factory, scope, _, _, _ = trace_database
    reader = SqlAlchemyVisionPolicyReader(factory)
    old_config, old_project = reader(scope.tenant_id, scope.project_id)
    with factory.begin():  # A legacy writer may remain open throughout these reads.
        policy("huggingface")
        with factory.begin() as session:
            session.get(ProjectExecutionPolicyModel, scope.project_id).allowed_origins = []
        config, project = reader(scope.tenant_id, scope.project_id)
    assert old_config["vision"]["provider"] == "gemini"
    assert config["vision"]["provider"] == "huggingface"
    assert old_project.allowed_origins == ["https://fixture.test"]
    assert project.allowed_origins == []
    assert reader("foreign", scope.project_id) == (None, None)
