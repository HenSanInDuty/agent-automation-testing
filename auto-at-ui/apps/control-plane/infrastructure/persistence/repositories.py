"""Tenant-scoped SQLAlchemy implementations of domain persistence ports."""

from datetime import datetime
from typing import cast
from uuid import UUID

from auto_at.contracts.agent import ProposalKind
from auto_at.contracts.execution import TestExecutionResult
from domain.entities import ApprovalRecord, ArtifactRecord, ProposalRecord
from domain.runs import AuditEvent, OutboxEvent, RunLifecycleStatus, TestRun
from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from infrastructure.persistence.models import (
    AgentProposalModel,
    ApprovalModel,
    ArtifactModel,
    AuditEventModel,
    ConfigurationModel,
    GeneratedTestDecisionModel,
    GeneratedTestDraftModel,
    GenerationRequestModel,
    OutboxEventModel,
    ProjectExecutionPolicyModel,
    TestCaseModel,
    TestRunModel,
)


class SqlAlchemyGenerationRepository:
    """Tenant-scoped persistence for governed generated-test records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_request_by_key(self, tenant_id: str, key: str) -> GenerationRequestModel | None:
        return self._session.scalar(
            select(GenerationRequestModel).where(
                GenerationRequestModel.tenant_id == tenant_id,
                GenerationRequestModel.idempotency_key == key,
            )
        )

    def get_request(self, tenant_id: str, request_id: UUID) -> GenerationRequestModel | None:
        return self._session.scalar(
            select(GenerationRequestModel).where(
                GenerationRequestModel.tenant_id == tenant_id,
                GenerationRequestModel.id == request_id,
            )
        )

    def claim_queued_request(
        self, tenant_id: str, request_id: UUID
    ) -> GenerationRequestModel | None:
        """Atomically claim queued work; retries never invoke a model twice."""
        model = self._session.scalar(
            select(GenerationRequestModel)
            .where(
                GenerationRequestModel.tenant_id == tenant_id,
                GenerationRequestModel.id == request_id,
            )
            .with_for_update()
        )
        if model is None or model.state != "queued":
            return None
        model.state = "generating"
        self._session.flush()
        return model

    def add_request(self, model: GenerationRequestModel) -> None:
        self._session.add(model)
        self._session.flush()

    def get_draft(self, tenant_id: str, draft_id: UUID) -> GeneratedTestDraftModel | None:
        return self._session.scalar(
            select(GeneratedTestDraftModel).where(
                GeneratedTestDraftModel.tenant_id == tenant_id,
                GeneratedTestDraftModel.id == draft_id,
            )
        )

    def get_draft_for_request(
        self, tenant_id: str, request_id: UUID
    ) -> GeneratedTestDraftModel | None:
        return self._session.scalar(
            select(GeneratedTestDraftModel).where(
                GeneratedTestDraftModel.tenant_id == tenant_id,
                GeneratedTestDraftModel.planning_request_id == request_id,
            )
        )

    def add_draft(self, model: GeneratedTestDraftModel) -> None:
        self._session.add(model)
        self._session.flush()

    def get_decision(self, tenant_id: str, draft_id: UUID) -> GeneratedTestDecisionModel | None:
        return self._session.scalar(
            select(GeneratedTestDecisionModel).where(
                GeneratedTestDecisionModel.tenant_id == tenant_id,
                GeneratedTestDecisionModel.draft_id == draft_id,
            )
        )

    def add_decision(self, model: GeneratedTestDecisionModel) -> None:
        self._session.add(model)
        self._session.flush()

    def get_policy(self, tenant_id: str, project_id: UUID) -> ProjectExecutionPolicyModel | None:
        return self._session.scalar(
            select(ProjectExecutionPolicyModel).where(
                ProjectExecutionPolicyModel.tenant_id == tenant_id,
                ProjectExecutionPolicyModel.project_id == project_id,
            )
        )

    def set_policy(self, tenant_id: str, project_id: UUID, origins: list[str]) -> None:
        model = self.get_policy(tenant_id, project_id)
        if model is None:
            self._session.add(
                ProjectExecutionPolicyModel(
                    tenant_id=tenant_id, project_id=project_id, allowed_origins=origins
                )
            )
        else:
            model.allowed_origins = origins
        self._session.flush()

    def add_test_case(self, model: TestCaseModel) -> None:
        self._session.add(model)
        self._session.flush()


class ConcurrentRunUpdateError(RuntimeError):
    """Raised when the expected optimistic version no longer matches."""


class SqlAlchemyRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: TestRun) -> None:
        self._session.add(
            TestRunModel(
                id=run.id,
                tenant_id=run.tenant_id,
                project_id=run.project_id,
                test_case_id=run.test_case_id,
                revision=run.revision,
                status=run.status.value,
                correlation_id=run.correlation_id,
                request=None,
                result=None,
                version=run.version,
            )
        )
        self._session.flush()

    def get(self, tenant_id: str, run_id: UUID) -> TestRun | None:
        statement = select(TestRunModel).where(
            TestRunModel.id == run_id, TestRunModel.tenant_id == tenant_id
        )
        model = self._session.scalar(statement)
        return None if model is None else self._to_domain(model)

    def save_result(self, run: TestRun, result: TestExecutionResult) -> None:
        expected_version = run.version
        run.record_runner_result(result)
        statement = (
            update(TestRunModel)
            .where(
                TestRunModel.id == run.id,
                TestRunModel.tenant_id == run.tenant_id,
                TestRunModel.version == expected_version,
            )
            .values(
                status=run.status.value,
                result=result.model_dump(mode="json"),
                version=run.version,
            )
        )
        if cast(CursorResult[object], self._session.execute(statement)).rowcount != 1:
            raise ConcurrentRunUpdateError("test run was updated by another transaction")

    def cancel(self, run: TestRun) -> None:
        expected_version = run.version
        run.cancel()
        statement = (
            update(TestRunModel)
            .where(
                TestRunModel.id == run.id,
                TestRunModel.tenant_id == run.tenant_id,
                TestRunModel.version == expected_version,
            )
            .values(status=run.status.value, version=run.version)
        )
        if cast(CursorResult[object], self._session.execute(statement)).rowcount != 1:
            raise ConcurrentRunUpdateError("test run was updated by another transaction")

    @staticmethod
    def _to_domain(model: TestRunModel) -> TestRun:
        result = None if model.result is None else TestExecutionResult.model_validate(model.result)
        return TestRun(
            id=model.id,
            tenant_id=model.tenant_id,
            project_id=model.project_id,
            test_case_id=model.test_case_id,
            revision=model.revision,
            correlation_id=model.correlation_id,
            status=RunLifecycleStatus(model.status),
            result=result,
            version=model.version,
        )


class SqlAlchemyOutboxEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> OutboxEvent | None:
        statement = select(OutboxEventModel).where(
            OutboxEventModel.tenant_id == tenant_id,
            OutboxEventModel.idempotency_key == idempotency_key,
        )
        model = self._session.scalar(statement)
        if model is None:
            return None
        return OutboxEvent(
            id=model.id,
            tenant_id=model.tenant_id,
            event_type=model.event_type,
            schema_version=model.schema_version,
            correlation_id=model.correlation_id,
            causation_id=model.causation_id,
            idempotency_key=model.idempotency_key,
            payload=model.payload,
        )

    def append(self, event: OutboxEvent) -> None:
        self._session.add(
            OutboxEventModel(
                id=event.id,
                tenant_id=event.tenant_id,
                event_type=event.event_type,
                schema_version=event.schema_version,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                idempotency_key=event.idempotency_key,
                payload=event.payload,
                published_at=None,
            )
        )
        self._session.flush()

    def list_unpublished(self, limit: int) -> list[OutboxEvent]:
        statement = (
            select(OutboxEventModel)
            .where(OutboxEventModel.published_at.is_(None))
            .order_by(OutboxEventModel.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [
            OutboxEvent(
                id=model.id,
                tenant_id=model.tenant_id,
                event_type=model.event_type,
                schema_version=model.schema_version,
                correlation_id=model.correlation_id,
                causation_id=model.causation_id,
                idempotency_key=model.idempotency_key,
                payload=model.payload,
            )
            for model in self._session.scalars(statement)
        ]

    def mark_published(self, event_id: UUID, published_at: datetime) -> None:
        self._session.execute(
            update(OutboxEventModel)
            .where(OutboxEventModel.id == event_id, OutboxEventModel.published_at.is_(None))
            .values(published_at=published_at)
        )


class SqlAlchemyArtifactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_run(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]:
        statement = select(ArtifactModel).where(
            ArtifactModel.tenant_id == tenant_id, ArtifactModel.run_id == run_id
        )
        return [
            ArtifactRecord(
                id=model.id,
                tenant_id=model.tenant_id,
                run_id=model.run_id,
                kind=model.kind,
                uri=model.uri,
                checksum=model.checksum,
                size=model.size,
                content_type=model.content_type,
                retention_until=model.retention_until,
            )
            for model in self._session.scalars(statement)
        ]

    def add(self, artifact: ArtifactRecord) -> None:
        self._session.add(
            ArtifactModel(
                id=artifact.id,
                tenant_id=artifact.tenant_id,
                run_id=artifact.run_id,
                kind=artifact.kind,
                uri=artifact.uri,
                checksum=artifact.checksum,
                size=artifact.size,
                content_type=artifact.content_type,
                retention_until=artifact.retention_until,
            )
        )
        self._session.flush()


class SqlAlchemyProposalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: str, proposal_id: UUID) -> ProposalRecord | None:
        model = self._session.scalar(
            select(AgentProposalModel).where(
                AgentProposalModel.id == proposal_id, AgentProposalModel.tenant_id == tenant_id
            )
        )
        if model is None:
            return None
        return ProposalRecord(
            id=model.id,
            tenant_id=model.tenant_id,
            run_id=model.run_id,
            correlation_id=model.correlation_id,
            kind=ProposalKind(model.kind),
            proposal_version=model.proposal_version,
            summary=model.summary,
            created_at=model.created_at,
            payload=model.proposal,
        )

    def add(self, proposal: ProposalRecord) -> None:
        self._session.add(
            AgentProposalModel(
                id=proposal.id,
                tenant_id=proposal.tenant_id,
                run_id=proposal.run_id,
                correlation_id=proposal.correlation_id,
                kind=proposal.kind.value,
                proposal_version=proposal.proposal_version,
                summary=proposal.summary,
                proposal=proposal.payload,
                created_at=proposal.created_at,
            )
        )
        self._session.flush()


class SqlAlchemyApprovalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_final(
        self, tenant_id: str, proposal_id: UUID, proposal_version: int
    ) -> ApprovalRecord | None:
        model = self._session.scalar(
            select(ApprovalModel).where(
                ApprovalModel.proposal_id == proposal_id,
                ApprovalModel.proposal_version == proposal_version,
                ApprovalModel.tenant_id == tenant_id,
            )
        )
        if model is None:
            return None
        return ApprovalRecord(
            id=model.id,
            tenant_id=model.tenant_id,
            proposal_id=model.proposal_id,
            proposal_version=model.proposal_version,
            approved=model.approved,
            decided_by=model.decided_by,
            decided_at=model.decided_at,
            reason=model.reason,
        )

    def add(self, approval: ApprovalRecord) -> None:
        self._session.add(
            ApprovalModel(
                id=approval.id,
                proposal_id=approval.proposal_id,
                proposal_version=approval.proposal_version,
                approved=approval.approved,
                decided_by=approval.decided_by,
                reason=approval.reason,
                decided_at=approval.decided_at,
                tenant_id=approval.tenant_id,
            )
        )
        self._session.flush()


class SqlAlchemyAuditEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: AuditEvent) -> None:
        self._session.add(
            AuditEventModel(
                id=event.id,
                tenant_id=event.tenant_id,
                actor=event.actor,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                correlation_id=event.correlation_id,
            )
        )
        self._session.flush()


class SqlAlchemyConfigurationRepository:
    """Database storage for validated, non-secret tenant configuration."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: str, key: str) -> dict[str, object] | None:
        statement = select(ConfigurationModel).where(
            ConfigurationModel.tenant_id == tenant_id, ConfigurationModel.key == key
        )
        model = self._session.scalar(statement)
        return None if model is None else model.value

    def set(self, tenant_id: str, key: str, value: dict[str, object]) -> None:
        statement = select(ConfigurationModel).where(
            ConfigurationModel.tenant_id == tenant_id, ConfigurationModel.key == key
        )
        model = self._session.scalar(statement)
        if model is None:
            self._session.add(ConfigurationModel(tenant_id=tenant_id, key=key, value=value))
        else:
            model.value = value
        self._session.flush()
