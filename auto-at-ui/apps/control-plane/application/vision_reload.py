"""Start a fresh exploration from a retained request without exposing its intent."""

from hashlib import sha256
from uuid import UUID

from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, resolve_agent_runtime
from agents.vision.intent import VisualIntentUnavailableError, decrypt_visual_intent
from config import Settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)

from application.vision import SubmitVisualExploration, VisionPolicyChanged, VisionStateError


class VisionReloadUnavailable(VisionStateError):
    pass


class ReloadVisualExploration:
    def __init__(self, repository, configs, submit: SubmitVisualExploration, settings: Settings):
        self.repository, self.configs, self.submit, self.settings = (
            repository, configs, submit, settings,
        )

    def execute(
        self, *, tenant_id: str, session_id: UUID, principal: Principal,
        idempotency_key: str, expected_provider: str, expected_model: str,
    ):
        original = self.repository.get(tenant_id, session_id)
        if original is None:
            raise AuthorizationError("Visual exploration not found")
        require(
            actor_for_tenant(principal, tenant_id, original.project_id),
            Permission.SUBMIT_GENERATION,
        )
        # A reload gets its own key namespace; transport retries still return one new session.
        key = "vision-reload:" + sha256(f"{session_id}:{idempotency_key}".encode()).hexdigest()
        existing = self.repository.get_by_key(tenant_id, key)
        if existing is not None:
            if (
                existing.project_id != original.project_id
                or existing.target_url != original.target_url
                or existing.intent_hash != original.intent_hash
            ):
                raise VisionStateError("idempotency key belongs to a different exploration")
            if (existing.provider, existing.model) != (expected_provider, expected_model):
                raise VisionPolicyChanged("vision_policy_changed")
            return existing
        if original.state not in {"completed", "unavailable", "cancelled"}:
            raise VisionReloadUnavailable("vision_reload_active")
        try:
            intent = decrypt_visual_intent(
                original.encrypted_task_intent, self.settings.vision_intent_encryption_key,
                original.intent_retention_until,
            )
        except VisualIntentUnavailableError:
            raise VisionReloadUnavailable("vision_reload_intent_unavailable") from None
        runtime = resolve_agent_runtime(
            self.settings, self.configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY),
        )
        return self.submit.execute(
            tenant_id=tenant_id, project_id=original.project_id, correlation_id=None,
            target_url=original.target_url, task_intent=intent, idempotency_key=key,
            runtime=runtime, actor=principal.subject,
            intent_encryption_key=self.settings.vision_intent_encryption_key,
            intent_retention_days=self.settings.vision_intent_retention_days,
            trace_v4_enabled=self.settings.vision_trace_v4_enabled,
            expected_provider=expected_provider, expected_model=expected_model,
        )
