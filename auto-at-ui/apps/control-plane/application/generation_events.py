"""Durable event consumer for advisory, governed test generation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from agents.generation.planner import plan_test
from agents.shared.openrouter import create_language_model
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, AgentStepGuard, resolve_agent_runtime
from auto_at.contracts.execution import sha256_text, validate_playwright_test_source
from auto_at.contracts.generation import (
    GeneratedTestDraft,
    PlanningProvenance,
    ProjectExecutionPolicy,
    TestGenerationPlanningRequest,
)
from config import Settings
from domain.activity import ActivityEvent
from domain.ports import ActivityEventRepository
from domain.runs import AuditEvent, OutboxEvent
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyGenerationRepository,
)

from application.generation import complete_generation, fail_generation

logger = logging.getLogger(__name__)


class GenerationEventProcessor:
    """Consumes one outbox event without authority to approve or dispatch tests."""

    def __init__(
        self,
        repository: SqlAlchemyGenerationRepository,
        configurations: SqlAlchemyConfigurationRepository,
        audits: SqlAlchemyAuditEventRepository,
        settings: Settings,
        activities: ActivityEventRepository | None = None,
    ) -> None:
        self._repository = repository
        self._configurations = configurations
        self._audits = audits
        self._settings = settings
        self._activities = activities

    async def execute(self, event: OutboxEvent) -> str:
        if event.event_type != "agent.test_generation.requested.v1":
            raise ValueError("unexpected event type for generation processor")
        raw_request_id = event.payload.get("request_id")
        if not isinstance(raw_request_id, str):
            raise ValueError("generation event is missing request_id")
        request_id = UUID(raw_request_id)
        request = self._repository.claim_queued_request(event.tenant_id, request_id)
        if request is None:
            return "already_processed"
        self._record(request, "claim", "running", "Generation request was claimed.")
        self._audits.append(
            AuditEvent(
                id=UUID(int=event.id.int ^ request_id.int),
                tenant_id=event.tenant_id,
                actor="test-generation-planner",
                action="generation.claimed",
                entity_type="generation_request",
                entity_id=request_id,
                correlation_id=request.correlation_id,
            )
        )
        try:
            policy_record = self._repository.get_policy(event.tenant_id, request.project_id)
            if policy_record is None:
                raise ValueError("project execution policy is unavailable")
            policy = ProjectExecutionPolicy(
                project_id=request.project_id, allowed_origins=policy_record.allowed_origins
            )
            if not policy.allows(request.target_url):
                raise ValueError("target URL origin is no longer allowed")
            planning_request = TestGenerationPlanningRequest(
                id=request.id,
                correlation_id=request.correlation_id,
                project_id=request.project_id,
                target_url=request.target_url,
                redacted_request=request.redacted_request,
                request_hash=request.request_hash,
            )
            runtime = resolve_agent_runtime(
                self._settings,
                self._configurations.get(event.tenant_id, AGENT_RUNTIME_CONFIG_KEY),
            )
            guard = AgentStepGuard(runtime.guard)
            if not guard.allow_next_step(
                requested_tokens=self._settings.agent_generation_max_tokens, evidence_bytes=0
            ):
                raise ValueError("generation token budget is exhausted")
            model = create_language_model(self._settings, runtime)
            self._record(request, "model", "running", "Generation model is producing a draft.")
            output = await plan_test(
                model,
                planning_request,
                policy.allowed_origins,
                self._settings.agent_generation_max_tokens,
            )
            validate_playwright_test_source(output.playwright_test_source)
            complete_generation(
                self._repository,
                tenant_id=event.tenant_id,
                request_id=request_id,
                draft=GeneratedTestDraft(
                    planning_request_id=request_id,
                    correlation_id=request.correlation_id,
                    title=output.title,
                    playwright_test_source=output.playwright_test_source,
                    source_hash=sha256_text(output.playwright_test_source),
                    assumptions=output.assumptions,
                    stop_conditions=output.stop_conditions,
                    provenance=PlanningProvenance(
                        provider=runtime.provider,
                        model=runtime.model,
                        prompt_version=self._settings.agent_generation_prompt_version,
                        redaction_policy_version=self._settings.agent_generation_redaction_policy_version,
                    ),
                ),
                audits=self._audits,
            )
            logger.info(
                "generation completed request_id=%s correlation_id=%s",
                request_id,
                request.correlation_id,
            )
            self._record(request, "completed", "passed", "Generation draft passed validation.")
            return "completed"
        except Exception as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            # Never persist provider responses or exception details: they may
            # contain unredacted data.
            detail = (
                "generation unavailable"
                if "configured" in str(error)
                else "generation output failed policy validation"
            )
            fail_generation(
                self._repository,
                tenant_id=event.tenant_id,
                request_id=request_id,
                reason=detail,
                audits=self._audits,
            )
            logger.warning(
                "generation failed request_id=%s correlation_id=%s reason=%s",
                request_id,
                request.correlation_id,
                type(error).__name__,
            )
            self._record(request, "failed", "failed", "Generation failed safely.")
            return "failed"

    def _record(self, request, stage: str, status: str, summary: str) -> None:
        if self._activities is not None:
            self._activities.append(ActivityEvent.create(
                tenant_id=request.tenant_id, correlation_id=request.correlation_id,
                source="generation", stage=stage, status=status, safe_summary=summary,
                occurred_at=datetime.now(UTC), metadata={"request_id": str(request.id)},
            ))
