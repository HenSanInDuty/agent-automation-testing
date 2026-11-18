"""Tenant-admin selection of the draft provider, independent of exploration/triage."""

from datetime import UTC, datetime
from uuid import uuid4

from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, resolve_agent_runtime
from auto_at.contracts.codex_bridge import content_hash
from auto_at.contracts.codex_generation import GenerationProviderPolicy
from domain.authorization import Permission, actor_for_tenant, require
from domain.runs import AuditEvent


class GenerationPolicyError(ValueError):
    pass


class GenerationPolicies:
    def __init__(self, settings, configs, audits, readiness):
        self.settings, self.configs, self.audits = settings, configs, audits
        self.readiness = readiness

    def read(self, tenant_id, principal):
        actor_for_tenant(principal, tenant_id)
        runtime = resolve_agent_runtime(
            self.settings, self.configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY),
        )
        return runtime.generation_policy()

    def configured(self, tenant_id, provider):
        if provider == "codex_cli":
            return self.readiness.read(tenant_id, datetime.now(UTC)).ready
        return bool(self.settings.huggingface_api_key if provider == "huggingface"
                    else self.settings.openrouter_api_key)

    def catalogue(self, tenant_id, principal):
        policy = self.read(tenant_id, principal)
        stored = self.configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY) or {}
        runtime = resolve_agent_runtime(
            self.settings, stored,
        )
        hf_model = runtime.model if runtime.provider == "huggingface" else (
            "Qwen/Qwen2.5-Coder-32B-Instruct"
        )
        items = [{"id": "codex_cli", "label": "Codex", "model": "gpt-6-luna"},
                 {"id": "huggingface", "label": "Hugging Face", "model": hf_model}]
        if policy.provider == "openrouter" or runtime.provider == "openrouter":
            items.append({"id": "openrouter", "label": "OpenRouter", "model": runtime.model})
        for item in items:
            remembered = stored.get("generation_models", {}).get(item["id"])
            if remembered:
                item["model"] = remembered
            if item["id"] == policy.provider:
                item["model"] = policy.model
            item["configured"] = self.configured(tenant_id, item["id"])
        return {"policy": policy.model_dump(mode="json"), "providers": items,
                "revision": content_hash(policy)}

    def update(self, tenant_id, principal, policy: GenerationProviderPolicy):
        require(actor_for_tenant(principal, tenant_id), Permission.MANAGE_TENANT)
        before = self.read(tenant_id, principal)
        if policy.text_transfer_accepted and not self.configured(tenant_id, policy.provider):
            raise GenerationPolicyError("generation provider unavailable")
        override = self.configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY) or {}
        models = {**override.get("generation_models", {}), before.provider: before.model,
                  policy.provider: policy.model}
        self.configs.set(tenant_id, AGENT_RUNTIME_CONFIG_KEY,
                         {**override, "generation": policy.model_dump(mode="json"),
                          "generation_models": models})
        audit_id = uuid4()
        self.configs.set(tenant_id, f"generation.policy.audit.v1.{audit_id}", {
            "before": before.model_dump(mode="json"), "after": policy.model_dump(mode="json"),
            "actor": principal.subject, "recorded_at": datetime.now(UTC).isoformat(),
        })
        self.audits.append(AuditEvent(
            id=audit_id, tenant_id=tenant_id, actor=principal.subject,
            action="generation.policy.updated", entity_type="generation_policy",
            entity_id=audit_id, correlation_id=uuid4(),
        ))
        return self.catalogue(tenant_id, principal)
