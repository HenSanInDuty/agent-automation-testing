"""HTTP policy reads/writes and provider discovery use synthetic configuration only."""

from uuid import UUID, uuid4

import pytest
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, VisionPolicy
from api.v1.dependencies.vision import vision_policies
from application.vision_policy import VISION_POLICY_AUDIT_PREFIX, VisionPolicies
from config import get_settings
from fastapi.testclient import TestClient
from main import app
from test_vision_policy import Audit, Configs, gemini_policy, settings


@pytest.fixture
def client():
    configs = Configs()
    audit = Audit()
    runtime_settings = settings(gemini_api_key="synthetic-secret")
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_settings] = lambda: runtime_settings
    app.dependency_overrides[vision_policies] = lambda: VisionPolicies(
        runtime_settings, configs, audit,
    )
    try:
        with TestClient(app) as client:
            client.configs, client.audit = configs, audit
            client.runtime_settings = runtime_settings
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.parametrize("path", ["policy", "providers"])
def test_read_requires_authentication(client, path):
    response = client.get(f"/api/v1/vision/{path}")
    assert response.status_code == 401


def test_provider_catalogue_is_readable_by_a_tenant_viewer(client):
    response = client.get("/api/v1/vision/providers", headers={
        "X-Tenant-Id": "tenant-a", "X-Actor-Roles": "viewer",
    })
    assert response.status_code == 200
    hf, gemini = response.json()["items"]
    assert not hf["configured"]
    assert gemini["configured"]
    assert gemini["id"] == "gemini"
    assert gemini["display_name"] == "Gehihi (Google Gemini)"
    assert "synthetic-secret" not in response.text
    assert "api_key" not in response.text


def test_disabled_policy_can_be_read_without_hf_key(client):
    response = client.get("/api/v1/vision/policy", headers={"X-Tenant-Id": "tenant-a"})
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["provider"] == "huggingface"
    assert response.json()["raw_screenshot_transfer_provider"] is None


def test_openapi_includes_provider_catalogue_and_consent_binding(client):
    schema = client.get("/openapi.json").json()
    assert "get" in schema["paths"]["/api/v1/vision/providers"]
    policy = schema["components"]["schemas"]["VisionPolicyResponse"]
    assert "raw_screenshot_transfer_provider" in policy["properties"]
    assert "gemini_api_key" not in str(schema)


def policy_payload(**changes):
    return {**VisionPolicy().model_dump(), **gemini_policy(), **changes}


def test_put_round_trip_is_tenant_scoped_and_correlated(client):
    correlation_id = uuid4()
    response = client.put("/api/v1/vision/policy", json=policy_payload(), headers={
        "X-Tenant-Id": "tenant-a", "X-Actor-Id": "fixture-admin",
        "X-Correlation-Id": str(correlation_id),
    })
    assert response.status_code == 200
    assert response.json()["raw_screenshot_transfer_provider"] == "gemini"
    assert client.get("/api/v1/vision/policy", headers={
        "X-Tenant-Id": "tenant-a",
    }).json() == response.json()
    assert client.get("/api/v1/vision/policy", headers={
        "X-Tenant-Id": "tenant-b",
    }).json()["enabled"] is False
    event, = client.audit.events
    assert event.actor == "fixture-admin"
    assert event.correlation_id == correlation_id == UUID(response.headers["X-Correlation-Id"])
    assert "synthetic-secret" not in response.text + str(client.configs.values)


@pytest.mark.parametrize("roles", ["viewer", "reviewer", "contributor", "project_admin", "service"])
def test_put_rejects_non_admin_without_writes(client, roles):
    response = client.put("/api/v1/vision/policy", json=policy_payload(), headers={
        "X-Tenant-Id": "tenant-a", "X-Actor-Roles": roles,
    })
    assert response.status_code == 403
    assert not client.configs.writes and not client.audit.events


def test_put_requires_authentication(client):
    assert client.put("/api/v1/vision/policy", json=policy_payload()).status_code == 401
    assert not client.configs.writes and not client.audit.events


@pytest.mark.parametrize("changes", [
    {"provider": "unknown"}, {"model": "gemini-other"}, {"max_steps": 0},
    {"raw_screenshot_transfer_accepted": False},
    {"raw_screenshot_transfer_provider": None},
    {"raw_screenshot_transfer_provider": "huggingface"},
])
def test_put_invalid_policy_returns_safe_422_and_no_writes(client, changes):
    response = client.put("/api/v1/vision/policy", json=policy_payload(**changes), headers={
        "X-Tenant-Id": "tenant-a",
    })
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "invalid_vision_policy"}
    assert not client.configs.writes and not client.audit.events


def test_put_missing_key_returns_409_but_disabled_policy_can_be_saved(client):
    client.runtime_settings.gemini_api_key = None
    response = client.put("/api/v1/vision/policy", json=policy_payload(), headers={
        "X-Tenant-Id": "tenant-a",
    })
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "provider_not_configured"}
    assert not client.configs.writes and not client.audit.events
    response = client.put("/api/v1/vision/policy", json=policy_payload(
        enabled=False, raw_screenshot_transfer_accepted=False,
    ), headers={"X-Tenant-Id": "tenant-a"})
    assert response.status_code == 200
    assert response.json()["raw_screenshot_transfer_provider"] is None
    assert len(client.audit.events) == 1


def test_old_hf_client_without_binding_remains_compatible(client):
    client.runtime_settings.huggingface_api_key = "synthetic-hf-secret"
    payload = policy_payload(provider="huggingface", model="custom/hf")
    del payload["raw_screenshot_transfer_provider"]
    response = client.put("/api/v1/vision/policy", json=payload, headers={
        "X-Tenant-Id": "tenant-a",
    })
    assert response.status_code == 200
    assert response.json()["raw_screenshot_transfer_provider"] == "huggingface"
    event, = client.audit.events
    snapshot = client.configs.get("tenant-a", VISION_POLICY_AUDIT_PREFIX + str(event.entity_id))
    assert snapshot["after"]["model"] == "custom/hf"
    assert client.configs.get("tenant-a", AGENT_RUNTIME_CONFIG_KEY)["vision"] == response.json()


@pytest.mark.parametrize("csrf_header", [None, "wrong-token"])
def test_cookie_write_requires_matching_csrf_without_writes(client, csrf_header):
    client.cookies.set("auto_at_session", "synthetic-session")
    client.cookies.set("auto_at_csrf", "synthetic-csrf")
    headers = {"X-Tenant-Id": "tenant-a"}
    if csrf_header:
        headers["X-CSRF-Token"] = csrf_header
    response = client.put("/api/v1/vision/policy", json=policy_payload(), headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed."
    assert not client.configs.writes and not client.audit.events
