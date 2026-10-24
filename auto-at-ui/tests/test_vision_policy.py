"""Offline policy/catalogue use cases; synthetic keys and tenant-scoped repositories."""

from copy import deepcopy
from uuid import uuid4

import pytest
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY
from application.vision_policy import VISION_POLICY_AUDIT_PREFIX, VisionPolicies, VisionPolicyError
from config import Settings
from domain.authorization import AuthorizationError, Principal, Role


class Configs:
    def __init__(self):
        self.values = {}
        self.writes = []

    def get(self, tenant_id, key):
        return deepcopy(self.values.get((tenant_id, key)))

    def set(self, tenant_id, key, value):
        self.values[tenant_id, key] = deepcopy(value)
        self.writes.append((tenant_id, key))


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


def principal(tenant="tenant-a", role=Role.TENANT_ADMIN):
    return Principal("synthetic-admin", {tenant: frozenset({role})}, {})


def gemini_policy(**changes):
    return {
        "enabled": True, "provider": "gemini", "model": "gemini-3.8-flash",
        "raw_screenshot_transfer_accepted": True,
        "raw_screenshot_transfer_provider": "gemini", **changes,
    }


def settings(**changes):
    return Settings(
        _env_file=None, vision_enabled=False, vision_provider="huggingface",
        vision_raw_screenshot_transfer_accepted=False,
        **{"huggingface_api_key": None, "gemini_api_key": None, **changes},
    )


def test_catalogue_preserves_custom_hf_models_and_exposes_only_readiness():
    configs = Configs()
    configs.values["tenant-a", AGENT_RUNTIME_CONFIG_KEY] = {"vision": {"model": "custom/hf"}}
    service = VisionPolicies(settings(gemini_api_key="synthetic-secret"), configs, Audit())
    hf, gemini, codex = service.providers("tenant-a", principal())
    assert codex["id"] == "codex_cli" and not codex["configured"]
    assert {item["id"] for item in hf["models"]} >= {"custom/hf"}
    assert not hf["configured"]
    assert gemini == {
        "id": "gemini", "display_name": "Gehihi (Google Gemini)",
        "models": [{"id": "gemini-3.8-flash", "display_name": "gemini-3.8-flash"}],
        "configured": True, "supports_inline_images": True,
    }
    assert "synthetic-secret" not in str([hf, gemini])
    assert not configs.writes


def test_codex_readiness_is_required_and_scoped_to_v4_without_image_consent():
    from test_codex_candidate_service import codex_policy
    from test_codex_model_batch import Readiness

    ready = Readiness()
    deployment = settings(vision_trace_v4_enabled=True)
    service = VisionPolicies(deployment, Configs(), Audit(), readiness=ready)
    value = codex_policy().model_dump(mode="json")
    assert service.validate_update("tenant-a", principal(), value).enabled
    assert service.providers("tenant-a", principal())[-1]["bridge_readiness"]["model_access"] == (
        "unverified"
    )
    ready.online = False
    with pytest.raises(VisionPolicyError, match="provider_not_configured"):
        service.validate_update("tenant-a", principal(), value)
    ready.online = True
    deployment.vision_trace_v4_enabled = False
    with pytest.raises(VisionPolicyError, match="provider_not_configured"):
        service.validate_update("tenant-a", principal(), value)


def test_missing_key_blocks_enablement_but_allows_disabled_configuration():
    service = VisionPolicies(settings(), Configs(), Audit())
    with pytest.raises(VisionPolicyError, match="provider_not_configured"):
        service.validate_update("tenant-a", principal(), gemini_policy())
    policy = service.validate_update("tenant-a", principal(), gemini_policy(
        enabled=False, raw_screenshot_transfer_accepted=False,
    ))
    assert not policy.enabled
    assert policy.raw_screenshot_transfer_provider is None


@pytest.mark.parametrize("role", [Role.VIEWER, Role.CONTRIBUTOR, Role.PROJECT_ADMIN, Role.SERVICE])
def test_non_admin_cannot_validate_update(role):
    service = VisionPolicies(settings(), Configs(), Audit())
    with pytest.raises(AuthorizationError):
        service.validate_update("tenant-a", principal(role=role), gemini_policy())


def test_catalogue_and_policy_reject_a_principal_from_another_tenant():
    service = VisionPolicies(settings(), Configs(), Audit())
    with pytest.raises(AuthorizationError):
        service.providers("tenant-b", principal())
    with pytest.raises(AuthorizationError):
        service.read("tenant-b", principal())


@pytest.mark.parametrize("changes", [
    {"provider": "unknown"}, {"model": "gemini-other"},
    {"raw_screenshot_transfer_provider": "huggingface"},
    {"raw_screenshot_transfer_provider": None}, {"max_steps": 0},
    {"api_key": "synthetic-secret"},
])
def test_invalid_policy_has_a_safe_error(changes):
    service = VisionPolicies(settings(gemini_api_key="synthetic-secret"), Configs(), Audit())
    with pytest.raises(VisionPolicyError) as failure:
        service.validate_update("tenant-a", principal(), gemini_policy(**changes))
    assert str(failure.value) == "invalid_vision_policy"


def test_updates_preserve_other_overrides_and_record_distinct_scoped_snapshots():
    configs, audit = Configs(), Audit()
    other = {
        "provider": "openrouter", "model": "custom/text",
        "evidence": {"include_metadata": False}, "guard": {"max_tokens": 1234},
        "fallback": {"provider": "huggingface", "model": "custom/fallback"},
    }
    configs.values["tenant-a", AGENT_RUNTIME_CONFIG_KEY] = deepcopy(other)
    configs.values["tenant-b", AGENT_RUNTIME_CONFIG_KEY] = {"model": "tenant-b/text"}
    service = VisionPolicies(settings(gemini_api_key="synthetic-secret"), configs, audit)
    before = service.read("tenant-a", principal()).model_dump(mode="json")
    correlation_id = uuid4()
    updated = service.update("tenant-a", principal(), gemini_policy(), correlation_id)

    assert configs.get("tenant-a", AGENT_RUNTIME_CONFIG_KEY) == {
        **other, "vision": updated.model_dump(mode="json"),
    }
    assert configs.get("tenant-b", AGENT_RUNTIME_CONFIG_KEY) == {"model": "tenant-b/text"}
    assert len(audit.events) == 1
    event = audit.events[0]
    assert (event.actor, event.tenant_id, event.correlation_id) == (
        principal().subject, "tenant-a", correlation_id,
    )
    assert event.action == "vision.policy.updated"
    assert event.entity_type == "vision_policy_snapshot"
    key = VISION_POLICY_AUDIT_PREFIX + str(event.entity_id)
    snapshot = configs.get("tenant-a", key)
    assert snapshot["before"] == before
    assert snapshot["after"] == updated.model_dump(mode="json")
    assert snapshot["schema_version"] == "vision-policy-audit-v1"
    assert snapshot["correlation_id"] == str(correlation_id)
    assert snapshot["actor"] == event.actor
    assert snapshot["tenant_id"] == event.tenant_id
    assert configs.get("tenant-b", key) is None

    service.update("tenant-a", principal(), gemini_policy(max_steps=7), uuid4())
    assert len(audit.events) == 2
    assert audit.events[1].entity_id != event.entity_id
    assert configs.get("tenant-a", key) == snapshot
    second = configs.get("tenant-a", VISION_POLICY_AUDIT_PREFIX + str(audit.events[1].entity_id))
    assert second["before"] == snapshot["after"]
    assert second["after"]["max_steps"] == 7
    assert "synthetic-secret" not in str(configs.values) + str(audit.events)
    assert "custom/text" not in str(snapshot)


@pytest.mark.parametrize("role", [
    Role.VIEWER, Role.CONTRIBUTOR, Role.REVIEWER, Role.PROJECT_ADMIN, Role.SERVICE,
])
def test_unauthorized_update_has_no_writes_or_audit(role):
    configs, audit = Configs(), Audit()
    service = VisionPolicies(settings(gemini_api_key="synthetic-secret"), configs, audit)
    with pytest.raises(AuthorizationError):
        service.update("tenant-a", principal(role=role), gemini_policy(), uuid4())
    assert not configs.writes and not audit.events


def test_cross_tenant_update_has_no_writes_or_audit():
    configs, audit = Configs(), Audit()
    service = VisionPolicies(settings(gemini_api_key="synthetic-secret"), configs, audit)
    with pytest.raises(AuthorizationError):
        service.update("tenant-b", principal(), gemini_policy(), uuid4())
    assert not configs.writes and not audit.events


def test_hf_consent_cannot_be_carried_into_gemini_update():
    configs, audit = Configs(), Audit()
    configs.values["tenant-a", AGENT_RUNTIME_CONFIG_KEY] = {"vision": {
        "enabled": True, "raw_screenshot_transfer_accepted": True,
    }}
    service = VisionPolicies(settings(gemini_api_key="synthetic-secret"), configs, audit)
    with pytest.raises(VisionPolicyError, match="invalid_vision_policy"):
        service.update("tenant-a", principal(), gemini_policy(
            raw_screenshot_transfer_provider=None,
        ), uuid4())
    assert not configs.writes and not audit.events
    service.update("tenant-a", principal(), gemini_policy(), uuid4())
    snapshot = configs.get("tenant-a", VISION_POLICY_AUDIT_PREFIX + str(audit.events[0].entity_id))
    assert snapshot["before"]["raw_screenshot_transfer_provider"] == "huggingface"
    assert snapshot["after"]["raw_screenshot_transfer_provider"] == "gemini"


def test_codex_cannot_inherit_hf_key_readiness():
    service = VisionPolicies(settings(huggingface_api_key="fixture"), Configs(), Audit())
    with pytest.raises(VisionPolicyError, match="provider_not_configured"):
        service.validate_update("tenant-a", principal(), {
            "enabled": True, "provider": "codex_cli", "model": "gpt-6-luna",
            "codex": {"dom_transfer_accepted": True, "dom_transfer_provider": "codex_cli"},
        })
