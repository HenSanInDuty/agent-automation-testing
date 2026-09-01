"""Use cases for advisory visual exploration; no model or browser calls occur here."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, AgentRuntimeConfig
from agents.vision.intent import encrypt_visual_intent
from auto_at.contracts.generation import ProjectExecutionPolicy, redact_generation_request
from domain.activity import ActivityEvent
from domain.runs import AuditEvent, OutboxEvent
from infrastructure.persistence.models import VisualExplorationSessionModel


class VisionStateError(ValueError):
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
        correlation_id: UUID,
        target_url: str,
        task_intent: str,
        idempotency_key: str,
        runtime: AgentRuntimeConfig,
        actor: str,
        intent_encryption_key: str | None,
        intent_retention_days: int,
    ) -> VisualExplorationSessionModel:
        policy = runtime.vision
        if not policy.enabled or not policy.raw_screenshot_transfer_accepted:
            raise VisionStateError("vision exploration is disabled by tenant policy")
        if redact_generation_request(task_intent) != task_intent:
            raise VisionStateError("task intent contains credentials and cannot be accepted")
        project = self._catalog.get_project(tenant_id, project_id)
        project_policy = self._generation.get_policy(tenant_id, project_id)
        if project is None or project.default_target != "web_ui":
            raise VisionStateError("vision exploration supports only web_ui projects")
        if project_policy is None or not ProjectExecutionPolicy(
            project_id=project_id, allowed_origins=project_policy.allowed_origins
        ).allows(target_url):
            raise VisionStateError(
                "target URL origin is not allowed by the project execution policy"
            )
        existing = self._repository.get_by_key(tenant_id, idempotency_key)
        intent_hash = hashlib.sha256(task_intent.encode("utf-8")).hexdigest()
        if existing is not None:
            if (
                existing.project_id != project_id
                or existing.target_url != target_url
                or existing.intent_hash != intent_hash
            ):
                raise VisionStateError("idempotency key belongs to a different exploration")
            return existing
        try:
            encrypted_intent = encrypt_visual_intent(task_intent, intent_encryption_key)
        except ValueError as error:
            raise VisionStateError("vision request encryption is not configured") from error
        now = datetime.now(UTC)
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
            prompt_version="vision-exploration-v2",
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
            ActivityEvent.create(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                source="vision",
                stage="queued",
                status="queued",
                safe_summary="Visual exploration queued.",
                metadata={"session_id": str(record.id), "policy_version": record.policy_version},
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
