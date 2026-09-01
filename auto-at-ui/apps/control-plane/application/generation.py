"""Governed lifecycle for generated Playwright test drafts.

The planner calls ``complete_generation`` later (Phase 2); this module owns no
model client and never gives the planner approval or dispatch authority.
"""

from uuid import UUID, uuid4

from auto_at.contracts.execution import (
    ArtifactPolicy,
    TargetType,
    TestExecutionRequest,
    sha256_text,
    validate_playwright_test_source,
)
from auto_at.contracts.generation import (
    DraftState,
    GeneratedTestDraft,
    ProjectExecutionPolicy,
    redact_generation_request,
    request_hash,
)
from domain.ports import GeneratedSourcePreflight
from domain.runs import AuditEvent, OutboxEvent
from infrastructure.persistence.models import (
    GeneratedTestDecisionModel,
    GeneratedTestDraftModel,
    GenerationRequestModel,
    TestCaseModel,
)
from infrastructure.persistence.repositories import SqlAlchemyGenerationRepository

from application.runs import CreateRun, CreateRunCommand


class GenerationNotFoundError(LookupError):
    pass


class GenerationStateError(ValueError):
    pass


class PreflightRepairQueued:
    """A safe repair request queued after source cannot load in the pinned worker."""

    def __init__(self, request_id: UUID) -> None:
        self.request_id = request_id


class SubmitGeneration:
    def __init__(self, repository: SqlAlchemyGenerationRepository, audits, outbox) -> None:
        self._repository, self._audits, self._outbox = repository, audits, outbox

    def execute(
        self,
        *,
        tenant_id: str,
        project_id: UUID,
        correlation_id: UUID,
        target_url: str,
        natural_language_request: str,
        idempotency_key: str,
    ):
        redacted = redact_generation_request(natural_language_request)
        if redacted != natural_language_request:
            raise ValueError("request contains credentials and cannot be accepted")
        policy = self._repository.get_policy(tenant_id, project_id)
        if policy is None or not ProjectExecutionPolicy(
            project_id=project_id, allowed_origins=policy.allowed_origins
        ).allows(target_url):
            raise ValueError("target URL origin is not allowed by the project execution policy")
        existing = self._repository.get_request_by_key(tenant_id, idempotency_key)
        if existing is not None:
            if (
                existing.project_id != project_id
                or existing.target_url != target_url
                or existing.request_hash != request_hash(redacted)
            ):
                raise GenerationStateError("idempotency key belongs to a different request")
            return existing
        record = GenerationRequestModel(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=correlation_id,
            target_url=target_url,
            redacted_request=redacted,
            request_hash=request_hash(redacted),
            state="queued",
            failure_reason=None,
            idempotency_key=idempotency_key,
        )
        self._repository.add_request(record)
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor="system",
                action="generation.requested",
                entity_type="generation_request",
                entity_id=record.id,
                correlation_id=correlation_id,
            )
        )
        self._outbox.append(
            OutboxEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                event_type="agent.test_generation.requested.v1",
                schema_version="v1",
                correlation_id=correlation_id,
                causation_id=None,
                idempotency_key=f"generation:{record.id}",
                payload={"request_id": str(record.id)},
            )
        )
        return record


def complete_generation(
    repository: SqlAlchemyGenerationRepository,
    *,
    tenant_id: str,
    request_id: UUID,
    draft: GeneratedTestDraft,
    audits=None,
) -> GeneratedTestDraftModel:
    """Internal planner handoff. It can only finish a queued request with one draft."""
    request = repository.get_request(tenant_id, request_id)
    if request is None:
        raise GenerationNotFoundError(request_id)
    if request.state == "completed":
        existing = repository.get_draft_for_request(tenant_id, request_id)
        if existing is None:
            raise GenerationStateError("completed request has no draft")
        return existing
    if request.state not in {"queued", "generating"} or draft.planning_request_id != request_id:
        raise GenerationStateError("generation request cannot be completed")
    if draft.correlation_id != request.correlation_id:
        raise GenerationStateError("generation draft correlation_id does not match request")
    validate_playwright_test_source(draft.playwright_test_source)
    record = GeneratedTestDraftModel(
        id=draft.id,
        tenant_id=tenant_id,
        planning_request_id=request_id,
        correlation_id=request.correlation_id,
        state=DraftState.PENDING_REVIEW.value,
        title=draft.title,
        playwright_test_source=draft.playwright_test_source,
        source_hash=draft.source_hash,
        assumptions=draft.assumptions,
        stop_conditions=draft.stop_conditions,
        provenance=draft.provenance.model_dump(mode="json"),
        linked_test_case_id=None,
        linked_run_id=None,
    )
    repository.add_draft(record)
    request.state = "completed"
    request.failure_reason = None
    if audits is not None:
        audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor="test-generation-planner",
                action="generation.completed",
                entity_type="generation_request",
                entity_id=request_id,
                correlation_id=request.correlation_id,
            )
        )
    return record


def fail_generation(
    repository: SqlAlchemyGenerationRepository,
    *,
    tenant_id: str,
    request_id: UUID,
    reason: str,
    audits,
) -> None:
    """Persist a safe terminal failure; diagnostics must already be redacted."""
    request = repository.get_request(tenant_id, request_id)
    if request is None:
        raise GenerationNotFoundError(request_id)
    if request.state in {"completed", "failed"}:
        return
    request.state = "failed"
    request.failure_reason = reason[:1_000]
    audits.append(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            actor="test-generation-planner",
            action="generation.failed",
            entity_type="generation_request",
            entity_id=request_id,
            correlation_id=request.correlation_id,
        )
    )


class DecideGeneratedDraft:
    def __init__(
        self, repository: SqlAlchemyGenerationRepository, audits, outbox, runs,
        preflight: GeneratedSourcePreflight | None = None,
    ) -> None:
        self._repository, self._audits, self._outbox, self._runs = repository, audits, outbox, runs
        self._preflight = preflight

    def execute(
        self, *, tenant_id: str, draft_id: UUID, approved: bool, decided_by: str, reason: str | None
    ):
        draft = self._repository.get_draft(tenant_id, draft_id)
        if draft is None:
            raise GenerationNotFoundError(draft_id)
        existing = self._repository.get_decision(tenant_id, draft_id)
        if existing is not None:
            if (
                existing.approved == approved
                and existing.decided_by == decided_by
                and existing.reason == reason
            ):
                return draft, existing
            raise GenerationStateError("draft already has an immutable final decision")
        if draft.state != DraftState.PENDING_REVIEW.value:
            raise GenerationStateError("only pending-review drafts can be decided")
        request = self._repository.get_request(tenant_id, draft.planning_request_id)
        if request is None or sha256_text(draft.playwright_test_source) != draft.source_hash:
            raise GenerationStateError("draft source integrity check failed")
        if approved:
            policy_record = self._repository.get_policy(tenant_id, request.project_id)
            if policy_record is None:
                raise GenerationStateError("project execution policy is required for approval")
            policy = ProjectExecutionPolicy(
                project_id=request.project_id, allowed_origins=policy_record.allowed_origins
            )
            test_case_id = f"generated-{draft.id}"
            runner_config = {
                "mode": "playwright_test_source",
                "playwright_test_source": draft.playwright_test_source,
                "source_hash": draft.source_hash,
                "allowed_origins": policy.allowed_origins,
            }
            if self._preflight is not None:
                try:
                    self._preflight.preflight(
                        TestExecutionRequest(
                            project_id=request.project_id,
                            test_case_id=test_case_id,
                            target_type=TargetType.WEB_UI,
                            target_url=request.target_url,
                            revision=draft.source_hash,
                            runner_config=runner_config,
                            artifact_policy=ArtifactPolicy(),
                        )
                    )
                except RuntimeError:
                    repair = SubmitGeneration(
                        self._repository, self._audits, self._outbox
                    ).execute(
                        tenant_id=tenant_id,
                        project_id=request.project_id,
                        correlation_id=request.correlation_id,
                        target_url=request.target_url,
                        natural_language_request=(
                            "Create a revised replacement for the generated "
                            "Playwright source below. "
                            "It failed non-browser preflight in the pinned Playwright runtime. "
                            "Preserve the testing intent and correct only the source issue. "
                            "Return a reviewable draft; do not change a test verdict.\n\n"
                            "Safe preflight failure: source could not load in "
                            "pinned Playwright Test.\n\n"
                            f"Generated source:\n{draft.playwright_test_source}"
                        ),
                        idempotency_key=f"preflight-repair:{draft.id}",
                    )
                    return draft, None, PreflightRepairQueued(repair.id)
            self._repository.add_test_case(
                TestCaseModel(
                    id=test_case_id,
                    tenant_id=tenant_id,
                    project_id=request.project_id,
                    target_type="web_ui",
                    revision=draft.source_hash,
                    specification={
                        "playwright_test_source": draft.playwright_test_source,
                        "source_hash": draft.source_hash,
                        "generated_draft_id": str(draft.id),
                    },
                    name=draft.title,
                )
            )
            run = CreateRun(self._runs, self._outbox, self._audits).execute(
                CreateRunCommand(
                    tenant_id=tenant_id,
                    project_id=request.project_id,
                    test_case_id=test_case_id,
                    revision=draft.source_hash,
                    correlation_id=request.correlation_id,
                    idempotency_key=f"generated-draft-run:{draft.id}",
                    target_type=TargetType.WEB_UI,
                    target_url=request.target_url,
                    runner_config=runner_config,
                    artifact_policy=ArtifactPolicy(),
                )
            )
            draft.linked_test_case_id, draft.linked_run_id = test_case_id, run.id
        decision = GeneratedTestDecisionModel(
            id=uuid4(),
            tenant_id=tenant_id,
            draft_id=draft.id,
            approved=approved,
            decided_by=decided_by,
            reason=reason,
        )
        self._repository.add_decision(decision)
        draft.state = DraftState.APPROVED.value if approved else DraftState.REJECTED.value
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor=decided_by,
                action="generated_draft.approved" if approved else "generated_draft.rejected",
                entity_type="generated_test_draft",
                entity_id=draft.id,
                correlation_id=draft.correlation_id,
            )
        )
        return draft, decision, None
