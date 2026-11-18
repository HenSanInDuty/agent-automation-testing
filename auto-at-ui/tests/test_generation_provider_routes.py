"""Tenant-scoped provider switching, audit and consent API checks."""

import pytest
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY
from api.v1.dependencies.generation_policy import generation_policies
from application.generation_policy import GenerationPolicies
from config import get_settings
from fastapi.testclient import TestClient
from main import app
from test_codex_generation import Ready, policy
from test_vision_policy import Audit, Configs, settings


@pytest.fixture
def client():
    config, audit = Configs(), Audit()
    runtime = settings(huggingface_api_key="synthetic")
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_settings] = lambda: runtime
    app.dependency_overrides[generation_policies] = lambda: GenerationPolicies(
        runtime, config, audit, Ready(),
    )
    try:
        with TestClient(app) as client:
            client.config, client.audit = config, audit
            yield client
    finally:
        app.dependency_overrides = previous


def test_provider_read_requires_auth(client):
    assert client.get("/api/v1/test-generations/provider").status_code == 401


@pytest.mark.parametrize("role", ["viewer", "contributor", "project_admin", "service"])
def test_only_admin_can_switch_provider(client, role):
    response = client.put("/api/v1/test-generations/provider", json=policy().model_dump(),
                          headers={"X-Tenant-Id": "tenant-a", "X-Actor-Roles": role})
    assert response.status_code == 403
    assert client.config.writes == []


def test_switch_round_trip_preserves_vision_and_other_tenants(client):
    key = ("tenant-a", AGENT_RUNTIME_CONFIG_KEY)
    client.config.values[key] = {"vision": {"enabled": False}, "model": "fixture/hf"}
    headers = {"X-Tenant-Id": "tenant-a", "X-Actor-Roles": "tenant_admin"}
    response = client.put("/api/v1/test-generations/provider", json=policy().model_dump(),
                          headers=headers)
    assert response.status_code == 200
    assert response.json()["policy"]["provider"] == "codex_cli"
    assert client.config.values[key]["vision"] == {"enabled": False}
    assert client.config.values[key]["model"] == "fixture/hf"
    foreign = client.get("/api/v1/test-generations/provider", headers={"X-Tenant-Id": "tenant-b"})
    assert foreign.json()["policy"]["provider"] == "huggingface"
    restored = client.put("/api/v1/test-generations/provider", headers=headers, json={
        "provider": "huggingface", "model": "fixture/hf", "text_transfer_accepted": True,
    })
    assert restored.status_code == 200
    assert restored.json()["policy"]["model"] == "fixture/hf"
    assert len(client.audit.events) == 2
    assert "synthetic" not in response.text
    client.put("/api/v1/test-generations/provider", headers=headers, json={
        "provider": "huggingface", "model": "fixture/custom-hf", "text_transfer_accepted": True,
    })
    remembered = client.put("/api/v1/test-generations/provider", headers=headers,
                            json=policy().model_dump()).json()
    assert next(item for item in remembered["providers"] if item["id"] == "huggingface")[
        "model"
    ] == "fixture/custom-hf"


def test_unrecognized_codex_model_rejected(client):
    response = client.put("/api/v1/test-generations/provider", headers={"X-Tenant-Id": "tenant-a"},
                          json={**policy().model_dump(), "model": "unapproved"})
    assert response.status_code == 422


def test_session_write_requires_csrf_before_changing_policy(client):
    client.cookies.set("auto_at_session", "synthetic-invalid-session")
    response = client.put("/api/v1/test-generations/provider", json=policy().model_dump(),
                          headers={"X-Tenant-Id": "tenant-a"})
    assert response.status_code == 403
    assert client.config.writes == []


def test_unavailable_provider_cannot_be_enabled_but_consent_can_be_revoked(client):
    from auto_at.contracts.codex_bridge import CodexBridgeReadiness
    class Offline:
        def read(self, *_):
            return CodexBridgeReadiness(configured=False, online=False, authenticated=False,
                                       capabilities_qualified=False)
    runtime = settings(huggingface_api_key="synthetic")
    app.dependency_overrides[generation_policies] = lambda: GenerationPolicies(
        runtime, client.config, client.audit, Offline(),
    )
    headers = {"X-Tenant-Id": "tenant-a"}
    response = client.put("/api/v1/test-generations/provider", json=policy().model_dump(),
                          headers=headers)
    assert response.status_code == 409 and client.config.writes == []
    revoked = client.put("/api/v1/test-generations/provider", headers=headers,
                         json=policy(text_transfer_accepted=False).model_dump())
    assert revoked.status_code == 200
    assert not revoked.json()["policy"]["text_transfer_accepted"]
