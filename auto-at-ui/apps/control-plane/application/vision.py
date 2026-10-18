"""Use cases for advisory visual exploration; no model or browser calls occur here."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from agents.prompts.vision import VISION_PROMPT_VERSION
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, AgentRuntimeConfig
from agents.vision.intent import encrypt_visual_intent
from auto_at.contracts.generation import (
    ProjectExecutionPolicy,
    origin_for_url,
    redact_generation_request,
)
from domain.activity import ActivityEvent
from domain.runs import AuditEvent, OutboxEvent
from infrastructure.persistence.models import VisualExplorationSessionModel


class VisionStateError(ValueError):
    pass


class VisionPolicyChanged(VisionStateError):
    pass


class SubmitVisualExploration:
    def __init__(self, repository, configs, catalog, generation, audits, activity, outbox) -> None:
        self._repository = repository
        self._configs = configs
        self._catalog = catalog
        self._generation = generation
        self._audits = audits
        self._activity = activity
        self._outbox = outbox

    def execute(
        self,
        *,
        tenant_id: str,
        project_id: UUID,
        correlation_id: UUID | None,
        target_url: str,
        task_intent: str,
        idempotency_key: str,
        runtime: AgentRuntimeConfig,
        actor: str,
        intent_encryption_key: str | None,
        intent_retention_days: int,
        trace_v4_enabled: bool = False,
        expected_provider: str | None = None,
        expected_model: str | None = None,
    ) -> VisualExplorationSessionModel:
        policy = runtime.vision
        if (expected_provider is None) != (expected_model is None):
            raise VisionStateError("expected_provider and expected_model must be supplied together")
        if redact_generation_request(task_intent) != task_intent:
            raise VisionStateError("task intent contains credentials and cannot be accepted")
        project = self._catalog.get_project(tenant_id, project_id)
        if project is None or project.default_target != "web_ui":
            raise VisionStateError("vision exploration supports only web_ui projects")
        existing = self._repository.get_by_key(tenant_id, idempotency_key)
        intent_hash = hashlib.sha256(task_intent.encode("utf-8")).hexdigest()
        if existing is not None:
            if (
                existing.tenant_id != tenant_id
                or existing.project_id != project_id
                or (correlation_id is not None and existing.correlation_id != correlation_id)
                or existing.target_url != target_url
                or existing.intent_hash != intent_hash
            ):
                raise VisionStateError("idempotency key belongs to a different exploration")
            if expected_provider is not None and (expected_provider, expected_model) != (
                existing.provider, existing.model
            ):
                raise VisionPolicyChanged("vision_policy_changed")
            return existing
        if expected_provider is not None and (expected_provider, expected_model) != (
            policy.provider, policy.model
        ):
            raise VisionPolicyChanged("vision_policy_changed")
        if policy.provider == "gemini" and expected_provider is None:
            raise VisionStateError("expected_provider and expected_model are required for Gemini")
        if (
            not policy.enabled or not policy.raw_screenshot_transfer_accepted
            or policy.raw_screenshot_transfer_provider != policy.provider
        ):
            raise VisionStateError("vision exploration is disabled by tenant policy")
        project_policy = self._generation.get_policy(tenant_id, project_id)
        try:
            origin_for_url(target_url)
        except ValueError:
            raise VisionStateError("target URL must be HTTP(S) without credentials") from None
        if project_policy is None:
            raise VisionStateError("project exploration limits are not configured")
        if (
            not trace_v4_enabled and (not project_policy.allowed_origins
            or not ProjectExecutionPolicy(
                project_id=project_id, allowed_origins=project_policy.allowed_origins
            ).allows(target_url))
        ):
            raise VisionStateError(
                "target URL origin is not allowed by the project execution policy"
            )
        try:
            encrypted_intent = encrypt_visual_intent(task_intent, intent_encryption_key)
        except ValueError as error:
            raise VisionStateError("vision request encryption is not configured") from error
        now = datetime.now(UTC)
        correlation_id = correlation_id or uuid4()
        record = VisualExplorationSessionModel(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=correlation_id,
            target_url=target_url,
            intent_hash=intent_hash,
            state="queued",
            encrypted_task_intent=encrypted_intent,
            intent_retention_until=now + timedelta(days=intent_retention_days),
            policy_version=AGENT_RUNTIME_CONFIG_KEY,
            provider=policy.provider,
            model=policy.model,
            prompt_version=VISION_PROMPT_VERSION,
            trace_version="v4" if trace_v4_enabled else "legacy",
            max_steps=policy.max_steps,
            max_hops=project_policy.vision_max_hops,
            max_states=project_policy.vision_max_states,
            max_screenshot_bytes=policy.max_screenshot_bytes,
            max_session_seconds=policy.max_session_seconds,
            max_cost_usd=str(policy.max_cost_usd),
            max_requests_per_minute=policy.max_requests_per_minute,
            safe_failure_reason=None,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(record)
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor=actor,
                action="vision.exploration_requested",
                entity_type="visual_exploration_session",
                entity_id=record.id,
                correlation_id=correlation_id,
            )
        )
        self._activity.append(
            ActivityEvent.create_vision_progress(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                visual_exploration_session_id=record.id,
                stage="queued",
                progress_key="queued",
                occurred_at=record.created_at,
            )
        )
        self._outbox.append(
            OutboxEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                event_type="agent.visual_exploration.requested.v1",
                schema_version="v1",
                correlation_id=correlation_id,
                causation_id=None,
                idempotency_key=f"vision:{record.id}",
                payload={"session_id": str(record.id)},
            )
        )
        return record
