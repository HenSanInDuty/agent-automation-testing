"""Tenant-scoped policy and catalogue use cases, with no HTTP or persistence clients."""

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, VisionPolicy, resolve_agent_runtime
from agents.shared.vision_providers import VISION_PROVIDERS, VisionProviderId
from config import Settings
from domain.authorization import Permission, Principal, actor_for_tenant, require
from domain.ports import AuditEventRepository, ConfigurationRepository
from domain.runs import AuditEvent
from pydantic import ValidationError

VISION_POLICY_AUDIT_PREFIX = "vision.policy.audit.v1."


class VisionPolicyError(ValueError):
    """Safe public policy error; never includes credentials or rejected input."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VisionPolicies:
    def __init__(
        self, settings: Settings, configs: ConfigurationRepository, audit: AuditEventRepository,
    ) -> None:
        self._settings = settings
        self._configs = configs
        self._audit = audit

    def read(self, tenant_id: str, principal: Principal) -> VisionPolicy:
        actor_for_tenant(principal, tenant_id)
        try:
            return resolve_agent_runtime(
                self._settings, self._configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY)
            ).vision
        except ValidationError as error:
            raise VisionPolicyError("invalid_vision_policy") from error

    def configured(self, provider: VisionProviderId) -> bool:
        key = (
            self._settings.gemini_api_key
            if provider == "gemini" else self._settings.huggingface_api_key
        )
        return bool(key and key.strip())

    def providers(self, tenant_id: str, principal: Principal) -> list[dict[str, object]]:
        policy = self.read(tenant_id, principal)
        items = []
        for provider in VISION_PROVIDERS:
            models = list(provider.models)
            if provider.id == "huggingface":
                # Both the deployment default and a tenant's custom HF model remain selectable.
                if self._settings.vision_provider == "huggingface":
                    models.append(self._settings.vision_model)
                if policy.provider == "huggingface":
                    models.append(policy.model)
            items.append({
                "id": provider.id,
                "display_name": provider.display_name,
                "models": [{"id": model, "display_name": model} for model in dict.fromkeys(models)],
                "configured": self.configured(provider.id),
                "supports_inline_images": provider.supports_inline_images,
            })
        return items

    def validate_update(
        self, tenant_id: str, principal: Principal, payload: Mapping[str, object],
    ) -> VisionPolicy:
        require(actor_for_tenant(principal, tenant_id), Permission.MANAGE_TENANT)
        try:
            policy = VisionPolicy.model_validate(payload)
        except ValidationError as error:
            raise VisionPolicyError("invalid_vision_policy") from error
        if policy.enabled and not self.configured(policy.provider):
            raise VisionPolicyError("provider_not_configured")
        return policy

    def update(
        self, tenant_id: str, principal: Principal, payload: Mapping[str, object],
        correlation_id: UUID,
    ) -> VisionPolicy:
        """The caller owns one transaction spanning config, snapshot and audit writes."""
        policy = self.validate_update(tenant_id, principal, payload)
        override = self._configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY) or {}
        try:
            before = resolve_agent_runtime(self._settings, override).vision
            # Preserve other tenant overrides exactly, including partial overrides.
            updated = {**override, "vision": policy.model_dump(mode="json")}
            resolve_agent_runtime(self._settings, updated)
        except ValidationError as error:
            raise VisionPolicyError("invalid_vision_policy") from error

        snapshot_id = uuid4()
        self._configs.set(tenant_id, AGENT_RUNTIME_CONFIG_KEY, updated)
        self._configs.set(tenant_id, VISION_POLICY_AUDIT_PREFIX + str(snapshot_id), {
            "schema_version": "vision-policy-audit-v1",
            "tenant_id": tenant_id,
            "actor": principal.subject,
            "correlation_id": str(correlation_id),
            "recorded_at": datetime.now(UTC).isoformat(),
            "before": before.model_dump(mode="json"),
            "after": policy.model_dump(mode="json"),
        })
        self._audit.append(AuditEvent(
            id=uuid4(), tenant_id=tenant_id, actor=principal.subject,
            action="vision.policy.updated", entity_type="vision_policy_snapshot",
            entity_id=snapshot_id, correlation_id=correlation_id,
        ))
        return policy
