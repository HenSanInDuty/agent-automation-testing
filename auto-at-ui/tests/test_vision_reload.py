"""Reload creates fresh, authorized sessions while preserving immutable old evidence."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from agents.vision.intent import decrypt_visual_intent, encrypt_visual_intent
from api.v1.dependencies import vision as dependencies
from api.v1.dependencies.authorization import current_principal
from application.vision_reload import ReloadVisualExploration, VisionReloadUnavailable
from config import Settings
from domain.authorization import AuthorizationError, Principal, Role
from infrastructure.persistence.models import VisualExplorationSessionModel
from main import app
from test_vision_provider_submission import counts, submission, submit  # noqa: F401

pytest_plugins = ["vision_trace_fixtures"]
KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.mark.parametrize("condition", ["missing", "viewer", "running", "expired"])
def test_reload_rejects_before_creating_any_request(condition):
    project, session_id = uuid4(), uuid4()
    source = SimpleNamespace(
        project_id=project, state="running" if condition == "running" else "completed",
        encrypted_task_intent=encrypt_visual_intent("Synthetic task", KEY),
        intent_retention_until=datetime.now(UTC) + timedelta(
            days=-1 if condition == "expired" else 1,
        ),
    )
    repository = Mock()
    repository.get.return_value = None if condition == "missing" else source
    repository.get_by_key.return_value = None
    submitter = Mock()
    principal = Principal("reader", {"tenant": frozenset({
        Role.VIEWER if condition == "viewer" else Role.CONTRIBUTOR,
    })}, {})
    service = ReloadVisualExploration(
        repository, Mock(), submitter, Settings(_env_file=None, vision_intent_encryption_key=KEY),
    )
    expected = AuthorizationError if condition in {"missing", "viewer"} else VisionReloadUnavailable
    with pytest.raises(expected):
        service.execute(
            tenant_id="tenant", session_id=session_id, principal=principal,
            idempotency_key="reload", expected_provider="gemini", expected_model="gemini-3.8-flash",
        )
    submitter.execute.assert_not_called()


@pytest.fixture
def reload_case(submission, trace_database, monkeypatch):  # noqa: F811
    client, payload, policy, settings = submission
    factory, scope, _, _, _ = trace_database
    monkeypatch.setattr(dependencies, "create_session_factory", lambda _: factory)
    saved = submit(client, payload).json()
    source_id = UUID(saved["id"])
    with factory.begin() as db:
        source = db.get(VisualExplorationSessionModel, source_id)
        source.state = "unavailable"
        source.safe_failure_reason = "model_output_invalid"

    def reload(key="reload-key", **changes):
        return client.post(
            f"/api/v1/vision/explorations/{source_id}/reload",
            headers={"Idempotency-Key": key},
            json={"expected_provider": "gemini", "expected_model": "gemini-3.8-flash", **changes},
        )
    return reload, factory, scope, source_id, payload, policy, settings


def test_reload_reuses_saved_request_and_creates_one_new_audited_session(reload_case):
    reload, factory, _, source_id, payload, _, settings = reload_case
    before = counts(factory)
    response = reload()
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["id"] != str(source_id) and result["state"] == "queued"
    assert "task_intent" not in result and "target_url" not in result
    with factory() as db:
        source = db.get(VisualExplorationSessionModel, source_id)
        new = db.get(VisualExplorationSessionModel, UUID(result["id"]))
        assert source.state == "unavailable"
        assert source.safe_failure_reason == "model_output_invalid"
        assert new.project_id == source.project_id and new.target_url == source.target_url
        assert new.correlation_id != source.correlation_id
        assert decrypt_visual_intent(
            new.encrypted_task_intent, settings.vision_intent_encryption_key,
            new.intent_retention_until,
        ) == payload["task_intent"]
    assert reload().json() == result
    assert counts(factory) == (before[0] + 1, before[1] + 1)


@pytest.mark.parametrize("condition", [
    "running", "expired", "viewer", "other_tenant", "policy", "disabled", "origin",
])
def test_reload_http_rechecks_access_retention_state_and_provider(reload_case, condition):
    reload, factory, scope, source_id, _, policy, _ = reload_case
    before = counts(factory)
    if condition in {"running", "expired", "other_tenant"}:
        with factory.begin() as db:
            source = db.get(VisualExplorationSessionModel, source_id)
            if condition == "running":
                source.state = "running"
            elif condition == "expired":
                source.intent_retention_until = datetime.now(UTC) - timedelta(seconds=1)
            else:
                source.tenant_id = "different-tenant"
    elif condition == "viewer":
        app.dependency_overrides[current_principal] = lambda: Principal(
            "reader", {scope.tenant_id: frozenset({Role.VIEWER})}, {},
        )
    elif condition == "policy":
        policy("huggingface")
    elif condition == "disabled":
        policy(enabled=False)
    else:
        from infrastructure.persistence.models import ProjectExecutionPolicyModel

        with factory.begin() as db:
            db.get(ProjectExecutionPolicyModel, scope.project_id).allowed_origins = []
    response = reload()
    expected = (
        404 if condition in {"viewer", "other_tenant"}
        else 422 if condition in {"disabled", "origin"} else 409
    )
    assert response.status_code == expected
    assert counts(factory) == before


def test_reload_cannot_supply_a_replacement_intent_or_target(reload_case):
    reload, factory, *_ = reload_case
    before = counts(factory)
    assert reload(task_intent="different").status_code == 422
    assert reload(target_url="https://other.invalid").status_code == 422
    assert counts(factory) == before
