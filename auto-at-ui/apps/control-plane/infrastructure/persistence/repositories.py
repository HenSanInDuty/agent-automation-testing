"""Tenant-scoped SQLAlchemy implementations of domain persistence ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from auto_at.contracts.agent import ProposalKind, RunReport, RunReportStatus
from auto_at.contracts.execution import RunStatus, TestExecutionRequest, TestExecutionResult
from auto_at.contracts.generation import VisionPlanningSource, vision_generation_key
from auto_at.contracts.vision import (
    VisualCheckpoint,
    VisualLocatorEvidence,
    VisualLocatorHandoff,
    VisualOperation,
    VisualOperationFrame,
)
from domain.activity import ActivityEvent
from domain.entities import (
    ApprovalRecord,
    ArtifactRecord,
    Project,
    ProposalRecord,
    RunReportRecord,
    TestCase,
    VisualOperationFrameRecord,
    VisualReplayFrameRecord,
    VisualTrajectoryEdgeRecord,
)
from domain.runs import AuditEvent, OutboxEvent, RunLifecycleStatus, TestRun
from domain.vision import VisualSessionLease, VisualSessionScope, validate_operation_transition
from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.orm import Session

from infrastructure.persistence.models import (
    ActivityEventModel,
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
    ProjectModel,
    RunReportModel,
    TestCaseModel,
    TestRunModel,
    VisionDebugEvidenceModel,
    VisualActionProposalModel,
    VisualExplorationSessionModel,
    VisualExplorationStateModel,
    VisualLocatorEvidenceModel,
    VisualLocatorHandoffModel,
    VisualOperationFrameModel,
    VisualOperationModel,
    VisualReplayFrameModel,
    VisualTrajectoryEdgeModel,
)


class SqlAlchemyCatalogRepository:
    """Tenant-scoped project and immutable test-case catalog persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_project(self, tenant_id: str, project_id: UUID) -> Project | None:
        model = self._session.scalar(
            select(ProjectModel).where(
                ProjectModel.tenant_id == tenant_id, ProjectModel.id == project_id
            )
        )
        return (
            None
            if model is None
            else Project(model.id, model.tenant_id, model.name, model.default_target)
        )

    def list_projects(self, tenant_id: str, query: str | None = None) -> list[Project]:
        statement = (
            select(ProjectModel)
            .where(ProjectModel.tenant_id == tenant_id)
            .order_by(ProjectModel.name)
        )
        if query:
            statement = statement.where(ProjectModel.name.ilike(f"%{query}%"))
        return [
            Project(item.id, item.tenant_id, item.name, item.default_target)
            for item in self._session.scalars(statement)
        ]

    def add_project(self, project: Project) -> None:
        self._session.add(
            ProjectModel(
                id=project.id,
                tenant_id=project.tenant_id,
                name=project.name,
                default_target=project.default_target.value,
            )
        )
        self._session.flush()

    def get_test_case(self, tenant_id: str, test_case_id: str) -> TestCase | None:
        model = self._session.scalar(
            select(TestCaseModel).where(
                TestCaseModel.tenant_id == tenant_id, TestCaseModel.id == test_case_id
            )
        )
        return (
            None
            if model is None
            else TestCase(
                model.id,
                model.tenant_id,
                model.project_id,
                model.target_type,
                model.revision,
                model.specification,
                model.name,
            )
        )

    def list_test_cases(
        self, tenant_id: str, project_id: UUID, query: str | None = None
    ) -> list[TestCase]:
        statement = (
            select(TestCaseModel)
            .where(TestCaseModel.tenant_id == tenant_id, TestCaseModel.project_id == project_id)
            .order_by(TestCaseModel.name, TestCaseModel.id)
        )
        if query:
            statement = statement.where(
                TestCaseModel.name.ilike(f"%{query}%") | TestCaseModel.id.ilike(f"%{query}%")
            )
        return [
            TestCase(
                item.id,
                item.tenant_id,
                item.project_id,
                item.target_type,
                item.revision,
                item.specification,
                item.name,
            )
            for item in self._session.scalars(statement)
        ]

    def add_test_case(self, test_case: TestCase) -> None:
        self._session.add(
            TestCaseModel(
                id=test_case.id,
                tenant_id=test_case.tenant_id,
                project_id=test_case.project_id,
                target_type=test_case.target_type.value,
                revision=test_case.revision,
                specification=test_case.specification,
                name=test_case.name,
            )
        )
        self._session.flush()

    def rename_test_case(self, tenant_id: str, test_case_id: str, name: str) -> TestCase | None:
        model = self._session.scalar(
            select(TestCaseModel).where(
                TestCaseModel.tenant_id == tenant_id, TestCaseModel.id == test_case_id
            )
        )
        if model is None:
            return None
        model.name = name
        self._session.flush()
        return TestCase(
            model.id,
            model.tenant_id,
            model.project_id,
            model.target_type,
            model.revision,
            model.specification,
            model.name,
        )


class SqlAlchemyGenerationRepository:
    """Tenant-scoped persistence for governed generated-test records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_vision_handoff(self, tenant_id, project_id, handoff_id):
        model = self._session.scalar(select(VisualLocatorHandoffModel).where(
            VisualLocatorHandoffModel.tenant_id == tenant_id,
            VisualLocatorHandoffModel.project_id == project_id,
            VisualLocatorHandoffModel.id == handoff_id,
        ))
        return VisualLocatorHandoff.model_validate(model.payload) if model else None

    def vision_evidence(self, tenant_id, project_id, handoff_id):
        handoff = self.get_vision_handoff(tenant_id, project_id, handoff_id)
        if handoff is None:
            raise ValueError("vision handoff scope mismatch")
        scope = VisualSessionScope(tenant_id, project_id, handoff.session_id)
        snapshot = SqlAlchemyVisualTraceRepository(self._session).snapshot(scope)
        actions = SqlAlchemyVisionRepository(self._session).list_actions(
            tenant_id, handoff.session_id
        )
        return handoff, snapshot, {item.id: item.action for item in actions}

    def validate_vision_target(self, handoff, target_url):
        record = self._session.scalar(select(VisualExplorationSessionModel).where(
            VisualExplorationSessionModel.tenant_id == handoff.tenant_id,
            VisualExplorationSessionModel.project_id == handoff.project_id,
            VisualExplorationSessionModel.id == handoff.session_id,
        ))
        if record is None or record.target_url != target_url:
            raise ValueError("vision handoff target mismatch")

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

    def list_requests(self, tenant_id: str) -> list[GenerationRequestModel]:
        return list(
            self._session.scalars(
                select(GenerationRequestModel)
                .where(GenerationRequestModel.tenant_id == tenant_id)
                .order_by(GenerationRequestModel.id.desc())
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
        if model.vision_handoff_id is not None:
            handoff = self._session.scalar(
                select(VisualLocatorHandoffModel).where(
                    VisualLocatorHandoffModel.id == model.vision_handoff_id,
                    VisualLocatorHandoffModel.tenant_id == model.tenant_id,
                    VisualLocatorHandoffModel.project_id == model.project_id,
                ).with_for_update()
            )
            if handoff is None:
                raise ValueError("generation handoff scope mismatch")
            payload = VisualLocatorHandoff.model_validate(handoff.payload)
            source = VisionPlanningSource(
                session_id=payload.session_id, handoff_id=payload.id,
                handoff_hash=payload.content_hash,
            )
            if model.idempotency_key != vision_generation_key(source, model.redacted_request):
                raise ValueError("generation idempotency must include handoff identity and hash")
            if handoff.generation_request_id not in (None, model.id):
                raise ValueError("handoff already linked to a generation request")
            handoff.generation_request_id = model.id
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

    def list_drafts(self, tenant_id: str) -> list[GeneratedTestDraftModel]:
        return list(
            self._session.scalars(
                select(GeneratedTestDraftModel)
                .where(GeneratedTestDraftModel.tenant_id == tenant_id)
                .order_by(GeneratedTestDraftModel.id.desc())
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

    def set_policy(
        self,
        tenant_id: str,
        project_id: UUID,
        origins: list[str],
        *,
        vision_max_hops: int = 5,
        vision_max_states: int = 50,
    ) -> None:
        model = self.get_policy(tenant_id, project_id)
        if model is None:
            self._session.add(
                ProjectExecutionPolicyModel(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    allowed_origins=origins,
                    vision_max_hops=vision_max_hops,
                    vision_max_states=vision_max_states,
                )
            )
        else:
            model.allowed_origins = origins
            model.vision_max_hops = vision_max_hops
            model.vision_max_states = vision_max_states
        self._session.flush()

    def add_test_case(self, model: TestCaseModel) -> None:
        self._session.add(model)
        self._session.flush()


class ConcurrentRunUpdateError(RuntimeError):
    """Raised when the expected optimistic version no longer matches."""


@dataclass(frozen=True)
class RunListItem:
    run: TestRun
    created_at: datetime


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
                request=None if run.request is None else run.request.model_dump(mode="json"),
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

    def list(self, tenant_id: str) -> list[RunListItem]:
        statement = (
            select(TestRunModel)
            .where(TestRunModel.tenant_id == tenant_id)
            .order_by(TestRunModel.created_at.desc(), TestRunModel.id.desc())
        )
        return [
            RunListItem(self._to_domain(model), model.created_at)
            for model in self._session.scalars(statement)
        ]

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
        request = (
            None if model.request is None else TestExecutionRequest.model_validate(model.request)
        )
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
            request=request,
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

    def list(self, tenant_id: str) -> list[ProposalRecord]:
        models = self._session.scalars(
            select(AgentProposalModel)
            .where(AgentProposalModel.tenant_id == tenant_id)
            .order_by(AgentProposalModel.created_at.desc(), AgentProposalModel.id.desc())
        )
        return [
            ProposalRecord(
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
            for model in models
        ]

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


class SqlAlchemyRunReportRepository:
    """Immutable, tenant-scoped run-report storage."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_run(
        self, tenant_id: str, run_id: UUID, report_version: int = 1
    ) -> RunReportRecord | None:
        model = self._session.scalar(
            select(RunReportModel).where(
                RunReportModel.tenant_id == tenant_id,
                RunReportModel.run_id == run_id,
                RunReportModel.report_version == report_version,
            )
        )
        return None if model is None else self._to_domain(model)

    def add(self, report: RunReportRecord) -> RunReportRecord:
        existing = self.get_for_run(report.tenant_id, report.run_id, report.report_version)
        if existing is not None:
            return existing
        self._session.add(
            RunReportModel(
                id=report.id,
                tenant_id=report.tenant_id,
                run_id=report.run_id,
                correlation_id=report.correlation_id,
                report_version=report.report_version,
                schema_version=report.schema_version,
                prompt_version=report.prompt_version,
                deterministic_status=report.deterministic_status.value,
                status=report.status.value,
                payload=None if report.payload is None else report.payload.model_dump(mode="json"),
                provenance=report.provenance,
                input_hash=report.input_hash,
                created_at=report.created_at,
            )
        )
        self._session.flush()
        return report

    @staticmethod
    def _to_domain(model: RunReportModel) -> RunReportRecord:
        return RunReportRecord(
            id=model.id,
            tenant_id=model.tenant_id,
            run_id=model.run_id,
            correlation_id=model.correlation_id,
            report_version=model.report_version,
            schema_version=model.schema_version,
            prompt_version=model.prompt_version,
            deterministic_status=RunStatus(model.deterministic_status),
            status=RunReportStatus(model.status),
            payload=None if model.payload is None else RunReport.model_validate(model.payload),
            provenance=model.provenance,
            input_hash=model.input_hash,
            created_at=model.created_at,
        )


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


class SqlAlchemyActivityEventRepository:
    """Append-only tenant-scoped observability timeline."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: ActivityEvent) -> None:
        if event.visual_exploration_session_id is not None and event.progress_key is not None:
            existing = self._session.scalar(
                select(ActivityEventModel.id).where(
                    ActivityEventModel.visual_exploration_session_id
                    == event.visual_exploration_session_id,
                    ActivityEventModel.progress_key == event.progress_key,
                )
            )
            if existing is not None:
                return
        self._session.add(
            ActivityEventModel(
                id=event.id,
                tenant_id=event.tenant_id,
                run_id=event.run_id,
                visual_exploration_session_id=event.visual_exploration_session_id,
                progress_key=event.progress_key,
                correlation_id=event.correlation_id,
                source=event.source,
                stage=event.stage,
                status=event.status,
                safe_summary=event.safe_summary,
                event_metadata=event.metadata,
                occurred_at=event.occurred_at,
            )
        )
        self._session.flush()

    def list(
        self,
        tenant_id: str,
        *,
        run_id: UUID | None = None,
        correlation_id: UUID | None = None,
        visual_exploration_session_id: UUID | None = None,
        after: datetime | None = None,
    ) -> list[ActivityEvent]:
        statement = select(ActivityEventModel).where(ActivityEventModel.tenant_id == tenant_id)
        if run_id is not None:
            statement = statement.where(ActivityEventModel.run_id == run_id)
        if correlation_id is not None:
            statement = statement.where(ActivityEventModel.correlation_id == correlation_id)
        if visual_exploration_session_id is not None:
            statement = statement.where(
                ActivityEventModel.visual_exploration_session_id == visual_exploration_session_id
            )
        if after is not None:
            statement = statement.where(ActivityEventModel.occurred_at > after)
        statement = statement.order_by(ActivityEventModel.occurred_at, ActivityEventModel.id)
        return [
            ActivityEvent(
                id=item.id,
                tenant_id=item.tenant_id,
                run_id=item.run_id,
                visual_exploration_session_id=item.visual_exploration_session_id,
                progress_key=item.progress_key,
                correlation_id=item.correlation_id,
                source=item.source,
                stage=item.stage,
                status=item.status,
                safe_summary=item.safe_summary,
                metadata=item.event_metadata,
                occurred_at=item.occurred_at,
            )
            for item in self._session.scalars(statement)
        ]


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

    def list_expired(self, before: datetime, limit: int) -> list[ArtifactRecord]:
        statement = (
            select(ArtifactModel)
            .where(
                ArtifactModel.retention_until.is_not(None), ArtifactModel.retention_until <= before
            )
            .order_by(ArtifactModel.retention_until, ArtifactModel.id)
            .limit(limit)
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

    def delete_expired(self, tenant_id: str, artifact_id: UUID) -> bool:
        result = self._session.execute(
            ArtifactModel.__table__.delete().where(
                ArtifactModel.id == artifact_id, ArtifactModel.tenant_id == tenant_id
            )
        )
        return bool(result.rowcount)


class SqlAlchemyVisualTraceRepository:
    """Short-transaction trace writes serialized by the fenced session row."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _scope(model, scope: VisualSessionScope):
        return (
            model.tenant_id == scope.tenant_id,
            model.project_id == scope.project_id,
            model.session_id == scope.session_id,
        )

    def claim(
        self, scope: VisualSessionScope, owner: UUID, *, lease_seconds: int = 30
    ) -> VisualSessionLease | None:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("invalid lease duration")
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=lease_seconds)
        token = self._session.scalar(
            update(VisualExplorationSessionModel)
            .where(
                VisualExplorationSessionModel.tenant_id == scope.tenant_id,
                VisualExplorationSessionModel.project_id == scope.project_id,
                VisualExplorationSessionModel.id == scope.session_id,
                VisualExplorationSessionModel.trace_version == "v4",
                VisualExplorationSessionModel.state.in_(["queued", "running"]),
                or_(
                    VisualExplorationSessionModel.lease_expires_at.is_(None),
                    VisualExplorationSessionModel.lease_expires_at <= now,
                ),
            )
            .values(
                lease_owner=owner,
                lease_expires_at=expires,
                fencing_token=VisualExplorationSessionModel.fencing_token + 1,
            )
            .returning(VisualExplorationSessionModel.fencing_token)
        )
        return None if token is None else VisualSessionLease(scope, owner, token, expires)

    def _fence(self, lease: VisualSessionLease) -> VisualExplorationSessionModel:
        scope = lease.scope
        model = self._session.scalar(
            select(VisualExplorationSessionModel)
            .where(
                VisualExplorationSessionModel.tenant_id == scope.tenant_id,
                VisualExplorationSessionModel.project_id == scope.project_id,
                VisualExplorationSessionModel.id == scope.session_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            model is None
            or model.trace_version != "v4"
            or model.lease_owner != lease.owner
            or model.fencing_token != lease.fencing_token
            or model.lease_expires_at is None
            or model.lease_expires_at <= datetime.now(UTC)
        ):
            raise ValueError("stale or expired visual session lease")
        return model

    def renew(self, lease: VisualSessionLease, *, lease_seconds: int = 30) -> VisualSessionLease:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("invalid lease duration")
        model = self._fence(lease)
        model.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        self._session.flush()
        return VisualSessionLease(
            lease.scope, lease.owner, lease.fencing_token, model.lease_expires_at
        )

    @staticmethod
    def _check_identity(value, scope: VisualSessionScope) -> None:
        if (value.tenant_id, value.project_id, value.session_id) != (
            scope.tenant_id,
            scope.project_id,
            scope.session_id,
        ):
            raise ValueError("trace reference scope mismatch")

    def _legacy_ref(self, model, scope: VisualSessionScope, identity: UUID | None):
        if identity is None:
            return None
        value = self._session.scalar(
            select(model).where(
                model.id == identity,
                model.tenant_id == scope.tenant_id,
                model.session_id == scope.session_id,
            )
        )
        if value is None:
            raise ValueError("state/proposal/edge reference scope mismatch")
        return value

    def _get(self, model, scope: VisualSessionScope, identity: UUID):
        return self._session.scalar(
            select(model).where(
                *self._scope(model, scope),
                model.id == identity,
            )
        )

    def _operation_refs(self, operation: VisualOperation, scope: VisualSessionScope) -> None:
        self._legacy_ref(VisualExplorationStateModel, scope, operation.state_id)
        proposal = self._legacy_ref(VisualActionProposalModel, scope, operation.proposal_id)
        edge = self._legacy_ref(VisualTrajectoryEdgeModel, scope, operation.edge_id)
        if proposal and proposal.originating_state_id != operation.state_id:
            raise ValueError("proposal does not belong to operation state")
        if edge and (
            edge.proposal_id != operation.proposal_id or edge.parent_state_id != operation.state_id
        ):
            raise ValueError("edge does not belong to operation proposal/state")
        if operation.checkpoint_id:
            # The restore destination may differ from the replay action's source state.
            checkpoints = self._session.scalars(select(VisualExplorationStateModel).where(
                VisualExplorationStateModel.tenant_id == scope.tenant_id,
                VisualExplorationStateModel.session_id == scope.session_id,
            ))
            if not any(s.checkpoint and s.checkpoint["id"] == str(operation.checkpoint_id)
                       for s in checkpoints):
                raise ValueError("checkpoint does not belong to operation session")
        if operation.parent_operation_id:
            parent = self._get(VisualOperationModel, scope, operation.parent_operation_id)
            if parent is None or parent.sequence >= operation.sequence:
                raise ValueError("parent must be an earlier operation in the same scope")
        for role in ("before", "after"):
            identity = getattr(operation, f"actual_{role}_frame_id")
            if identity:
                frame = self._get(VisualOperationFrameModel, scope, identity)
                if frame is None or frame.operation_id != operation.id or frame.role != role:
                    raise ValueError("operation frame reference mismatch")
                if operation.status == "executing" and frame.deleted_at is not None:
                    raise ValueError("cannot execute with deleted before evidence")
        if operation.locator_id:
            locator = self._get(VisualLocatorEvidenceModel, scope, operation.locator_id)
            if (
                locator is None
                or locator.operation_id != operation.id
                or locator.originating_frame_id != operation.actual_before_frame_id
                or (operation.status in {"executing", "completed"} and locator.status != "verified")
            ):
                raise ValueError("operation requires its own verified before-frame locator")
        if operation.status == "executing" and operation.action_kind in {"click", "type"}:
            if operation.locator_id is None:
                raise ValueError("targeted operation requires a verified locator")

    def prepare(self, lease: VisualSessionLease, operation: VisualOperation) -> VisualOperation:
        operation = VisualOperation.model_validate(operation.model_dump())
        model = self._fence(lease)
        self._check_identity(operation, lease.scope)
        existing = self._get(VisualOperationModel, lease.scope, operation.id)
        if existing:
            if existing.payload != operation.model_dump(mode="json"):
                raise ValueError("duplicate operation differs from persisted intent")
            return VisualOperation.model_validate(existing.payload)
        if operation.status != "prepared" or operation.sequence != model.next_operation_sequence:
            raise ValueError("new operation requires prepared status and next sequence")
        if (
            operation.actual_before_frame_id
            or operation.actual_after_frame_id
            or operation.locator_id
        ):
            raise ValueError("new operation cannot reference evidence before insertion")
        self._operation_refs(operation, lease.scope)
        self._session.add(
            VisualOperationModel(
                id=operation.id,
                tenant_id=operation.tenant_id,
                project_id=operation.project_id,
                session_id=operation.session_id,
                sequence=operation.sequence,
                attempt=operation.attempt,
                state_id=operation.state_id,
                proposal_id=operation.proposal_id,
                status=operation.status,
                fencing_token=lease.fencing_token,
                payload=operation.model_dump(mode="json"),
            )
        )
        model.next_operation_sequence += 1
        self._session.flush()
        return operation

    def save_operation(
        self, lease: VisualSessionLease, operation: VisualOperation
    ) -> VisualOperation:
        operation = VisualOperation.model_validate(operation.model_dump())
        self._fence(lease)
        self._check_identity(operation, lease.scope)
        model = self._get(VisualOperationModel, lease.scope, operation.id)
        if model is None:
            raise ValueError("operation must be prepared first")
        old = VisualOperation.model_validate(model.payload)
        validate_operation_transition(old, operation)
        if model.fencing_token != lease.fencing_token and old != operation:
            # A replacement worker cannot know whether the old browser side effect happened.
            if operation.status != "unknown":
                raise ValueError("reclaimed operation can only finalize unknown")
        self._operation_refs(operation, lease.scope)
        model.payload = operation.model_dump(mode="json")
        model.status = operation.status
        self._session.flush()
        return operation

    @staticmethod
    def _frame_record(model: VisualOperationFrameModel) -> VisualOperationFrameRecord:
        metadata = VisualOperationFrame.model_validate(
            {
                key: getattr(model, key)
                for key in VisualOperationFrame.model_fields
                if key != "schema_version"
            }
        )
        return VisualOperationFrameRecord(metadata, model.storage_key)

    def add_frame(
        self, lease: VisualSessionLease, record: VisualOperationFrameRecord
    ) -> VisualOperationFrameRecord:
        self._fence(lease)
        frame = VisualOperationFrame.model_validate(record.metadata.model_dump())
        self._check_identity(frame, lease.scope)
        operation = self._get(VisualOperationModel, lease.scope, frame.operation_id)
        if operation is None or operation.fencing_token != lease.fencing_token:
            raise ValueError("frame requires current operation owner")
        existing = self._session.scalar(
            select(VisualOperationFrameModel).where(
                VisualOperationFrameModel.operation_id == frame.operation_id,
                VisualOperationFrameModel.role == frame.role,
            )
        )
        if existing:
            if self._frame_record(existing) != record:
                raise ValueError("operation frame is immutable; checksum/identity conflict")
            return record
        if operation.status != ("prepared" if frame.role == "before" else "executing"):
            raise ValueError("frame capture is outside operation lifecycle")
        if frame.deleted_at is not None:
            raise ValueError("new frame cannot already be deleted")
        started = VisualOperation.model_validate(operation.payload).started_at
        if frame.captured_at < started:
            raise ValueError("frame predates this operation")
        self._session.add(
            VisualOperationFrameModel(
                **frame.model_dump(exclude={"schema_version"}),
                storage_key=record.storage_key,
            )
        )
        self._session.flush()
        return record

    def add_locator(
        self, lease: VisualSessionLease, evidence: VisualLocatorEvidence
    ) -> VisualLocatorEvidence:
        evidence = VisualLocatorEvidence.model_validate(evidence.model_dump())
        self._fence(lease)
        self._check_identity(evidence, lease.scope)
        operation = self._get(VisualOperationModel, lease.scope, evidence.operation_id)
        frame = self._get(VisualOperationFrameModel, lease.scope, evidence.originating_frame_id)
        if (
            operation is None
            or frame is None
            or frame.deleted_at is not None
            or frame.operation_id != evidence.operation_id
            or frame.role != "before"
            or operation.state_id != evidence.state_id
            or operation.proposal_id != evidence.proposal_id
        ):
            raise ValueError("locator source frame/state/proposal mismatch")
        if evidence.verified_at and evidence.verified_at < frame.captured_at:
            raise ValueError("locator verification predates originating frame")
        existing = self._get(VisualLocatorEvidenceModel, lease.scope, evidence.id)
        if existing:
            if existing.payload != evidence.model_dump(mode="json"):
                raise ValueError("locator evidence is immutable")
            return evidence
        if operation.status != "prepared" or operation.fencing_token != lease.fencing_token:
            raise ValueError("locator requires a prepared operation owned by current lease")
        self._session.add(
            VisualLocatorEvidenceModel(
                **{
                    key: getattr(evidence, key)
                    for key in (
                        "id",
                        "tenant_id",
                        "project_id",
                        "session_id",
                        "operation_id",
                        "state_id",
                        "proposal_id",
                        "originating_frame_id",
                        "status",
                    )
                },
                payload=evidence.model_dump(mode="json"),
            )
        )
        self._session.flush()
        return evidence

    def save_checkpoint(self, lease: VisualSessionLease, checkpoint: VisualCheckpoint) -> None:
        checkpoint = VisualCheckpoint.model_validate(checkpoint.model_dump())
        self._fence(lease)
        state = self._legacy_ref(VisualExplorationStateModel, lease.scope, checkpoint.state_id)
        previous = None
        for identity in checkpoint.ancestor_operation_ids:
            operation = self._get(VisualOperationModel, lease.scope, identity)
            if operation is None or operation.status != "completed":
                raise ValueError("checkpoint requires completed ancestor operations")
            payload = VisualOperation.model_validate(operation.payload)
            if payload.parent_operation_id != previous:
                raise ValueError("checkpoint ancestors must form one branch")
            previous = identity
        payload = checkpoint.model_dump(mode="json")
        if state.checkpoint is not None and state.checkpoint != payload:
            raise ValueError("checkpoint invariants are immutable")
        state.checkpoint = payload
        self._session.flush()

    def add_handoff(
        self, lease: VisualSessionLease, handoff: VisualLocatorHandoff
    ) -> VisualLocatorHandoff:
        handoff = VisualLocatorHandoff.model_validate(handoff.model_dump())
        self._fence(lease)
        self._check_identity(handoff, lease.scope)
        existing = self._session.scalar(
            select(VisualLocatorHandoffModel).where(
                *self._scope(VisualLocatorHandoffModel, lease.scope),
                VisualLocatorHandoffModel.version == handoff.version,
            )
        )
        if existing:
            if existing.payload != handoff.model_dump(mode="json"):
                raise ValueError("handoff version is immutable")
            return handoff
        for branch in handoff.branches:
            previous = None
            for step in branch.steps:
                model = self._get(VisualOperationModel, lease.scope, step.operation_id)
                if model is None or (branch.status == "ready" and model.status != "completed"):
                    raise ValueError("handoff requires completed operations in the same scope")
                operation = VisualOperation.model_validate(model.payload)
                if operation.parent_operation_id != previous:
                    raise ValueError("handoff must contain a complete branch, never siblings")
                previous = operation.id
                if step.locator_id != operation.locator_id:
                    raise ValueError("handoff locator must match executed operation")
                if (branch.status == "ready" and operation.action_kind in {"click", "type"}
                    and step.locator_id is None):
                    raise ValueError("targeted handoff step requires a verified locator")
                if (operation.action_kind == "type") != (step.input_reference is not None):
                    raise ValueError("typed handoff step requires an unbound input reference")
                self._operation_refs(operation, lease.scope)
        self._session.add(
            VisualLocatorHandoffModel(
                id=handoff.id,
                tenant_id=handoff.tenant_id,
                project_id=handoff.project_id,
                session_id=handoff.session_id,
                version=handoff.version,
                content_hash=handoff.content_hash,
                payload=handoff.model_dump(mode="json"),
                created_at=handoff.created_at,
            )
        )
        self._session.flush()
        return handoff

    def snapshot(self, scope: VisualSessionScope) -> dict[str, tuple]:
        """Return detached contracts, including frame tombstones, from one DB snapshot."""
        operations = self._session.scalars(
            select(VisualOperationModel)
            .where(
                *self._scope(VisualOperationModel, scope),
            )
            .order_by(VisualOperationModel.sequence)
        )
        frames = self._session.scalars(
            select(VisualOperationFrameModel)
            .where(
                *self._scope(VisualOperationFrameModel, scope),
            )
            .order_by(VisualOperationFrameModel.captured_at, VisualOperationFrameModel.id)
        )
        locators = self._session.scalars(
            select(VisualLocatorEvidenceModel)
            .where(
                *self._scope(VisualLocatorEvidenceModel, scope),
            )
            .order_by(VisualLocatorEvidenceModel.id)
        )
        handoffs = self._session.scalars(
            select(VisualLocatorHandoffModel)
            .where(
                *self._scope(VisualLocatorHandoffModel, scope),
            )
            .order_by(VisualLocatorHandoffModel.version)
        )
        return {
            "operations": tuple(VisualOperation.model_validate(row.payload) for row in operations),
            "frames": tuple(self._frame_record(row) for row in frames),
            "locators": tuple(
                VisualLocatorEvidence.model_validate(row.payload) for row in locators
            ),
            "handoffs": tuple(VisualLocatorHandoff.model_validate(row.payload) for row in handoffs),
        }

    def result_links(self, scope, *, legacy=False):
        generation = SqlAlchemyGenerationRepository(self._session)
        links = {
            key: {"state": "not_started", "id": None, "href": None}
            for key in ("handoff", "generation", "draft", "run", "report")
        }
        handoff = self._session.scalar(
            select(VisualLocatorHandoffModel)
            .where(*self._scope(VisualLocatorHandoffModel, scope))
            .order_by(VisualLocatorHandoffModel.version.desc())
        )
        request = None
        if handoff:
            package = VisualLocatorHandoff.model_validate(handoff.payload)
            links["handoff"] = dict(
                id=str(handoff.id),
                href=None,
                state="ready"
                if any(b.status == "ready" for b in package.branches)
                else "unavailable",
            )
            if handoff.generation_request_id:
                candidate = generation.get_request(scope.tenant_id, handoff.generation_request_id)
                if candidate and candidate.vision_handoff_id == handoff.id:
                    request = candidate
        elif legacy:
            request = generation.get_request_by_key(
                scope.tenant_id, f"vision-draft:{scope.session_id}"
            )
            links["handoff"]["state"] = "legacy_missing"
        if request is None or request.project_id != scope.project_id:
            record = SqlAlchemyVisionRepository(self._session).get(
                scope.tenant_id, scope.session_id
            )
            if record.state in {"completed", "unavailable", "cancelled"}:
                links["generation"]["state"] = "unavailable" if not legacy else "legacy_missing"
                if not legacy and handoff is None:
                    links["handoff"]["state"] = "unavailable"
            activity = self._session.scalar(select(ActivityEventModel).where(
                ActivityEventModel.tenant_id == scope.tenant_id,
                ActivityEventModel.visual_exploration_session_id == scope.session_id,
                ActivityEventModel.stage == "handoff.unavailable",
            ))
            if activity and activity.event_metadata.get("reason_code") in {
                "handoff_branch_limit", "handoff_incomplete", "no_eligible_branches",
                "generation_request_unavailable",
            }:
                links["handoff"]["reason_code"] = activity.event_metadata["reason_code"]
            return links
        links["generation"] = dict(
            state=request.state,
            id=str(request.id),
            href=None,
            reason_code="generation_unavailable" if request.state == "failed" else None,
        )
        draft = generation.get_draft_for_request(scope.tenant_id, request.id)
        if draft is None:
            return links
        links["draft"] = dict(state=draft.state, id=str(draft.id), href=f"/agent?draft={draft.id}")
        if draft.linked_run_id is None:
            return links
        run = self._session.scalar(
            select(TestRunModel).where(
                TestRunModel.tenant_id == scope.tenant_id,
                TestRunModel.project_id == scope.project_id,
                TestRunModel.id == draft.linked_run_id,
            )
        )
        if run is None:
            links["run"]["state"] = "unavailable"
            return links
        links["run"] = dict(state=run.status, id=str(run.id), href=f"/runs/{run.id}")
        report = self._session.scalar(
            select(RunReportModel)
            .where(
                RunReportModel.tenant_id == scope.tenant_id,
                RunReportModel.run_id == run.id,
            )
            .order_by(RunReportModel.report_version.desc())
        )
        pending_report = self._session.scalar(select(OutboxEventModel.id).where(
            OutboxEventModel.tenant_id == scope.tenant_id,
            OutboxEventModel.idempotency_key == f"run-report:{run.id}:v1",
            OutboxEventModel.published_at.is_(None),
        ))
        links["report"] = dict(
            state=("available" if report.status == "completed" else "unavailable")
            if report
            else "pending" if pending_report
            else "unavailable"
            if run.status in {"passed", "failed", "cancelled", "errored", "skipped"}
            else "pending",
            id=str(report.id) if report else None,
            href=f"/runs/{run.id}" if report else None,
        )
        return links

    def tombstone_frame(self, scope: VisualSessionScope, frame_id: UUID) -> bool:
        # Authorization is supplied by the application, separately from worker ownership.
        result = self._session.execute(
            update(VisualOperationFrameModel)
            .where(
                *self._scope(VisualOperationFrameModel, scope),
                VisualOperationFrameModel.id == frame_id,
                VisualOperationFrameModel.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(UTC))
        )
        return bool(result.rowcount)


class SqlAlchemyVisionRepository:
    """Tenant-scoped visual session persistence; values are safe metadata only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: str, session_id: UUID) -> VisualExplorationSessionModel | None:
        return self._session.scalar(
            select(VisualExplorationSessionModel).where(
                VisualExplorationSessionModel.tenant_id == tenant_id,
                VisualExplorationSessionModel.id == session_id,
            )
        )

    def get_by_key(self, tenant_id: str, key: str) -> VisualExplorationSessionModel | None:
        return self._session.scalar(
            select(VisualExplorationSessionModel).where(
                VisualExplorationSessionModel.tenant_id == tenant_id,
                VisualExplorationSessionModel.idempotency_key == key,
            )
        )

    def list(
        self, tenant_id: str, project_id: UUID | None = None
    ) -> list[VisualExplorationSessionModel]:
        statement = select(VisualExplorationSessionModel).where(
            VisualExplorationSessionModel.tenant_id == tenant_id
        )
        if project_id is not None:
            statement = statement.where(VisualExplorationSessionModel.project_id == project_id)
        return list(
            self._session.scalars(
                statement.order_by(VisualExplorationSessionModel.created_at.desc())
            )
        )

    def add(self, session: VisualExplorationSessionModel) -> None:
        self._session.add(session)
        self._session.flush()

    @staticmethod
    def _replay_frame_record(model: VisualReplayFrameModel) -> VisualReplayFrameRecord:
        return VisualReplayFrameRecord(
            id=model.id, tenant_id=model.tenant_id, session_id=model.session_id,
            state_id=model.state_id, sequence=model.sequence, storage_key=model.storage_key,
            checksum=model.checksum, size=model.size, content_type=model.content_type,
            captured_at=model.captured_at, deleted_at=model.deleted_at,
        )

    def add_replay_frame(self, frame: VisualReplayFrameRecord) -> VisualReplayFrameRecord:
        """Insert once per state; a replayed event must match immutable evidence."""
        existing = self._session.scalar(
            select(VisualReplayFrameModel).where(
                VisualReplayFrameModel.session_id == frame.session_id,
                VisualReplayFrameModel.state_id == frame.state_id,
            )
        )
        if existing is not None:
            fields = ("tenant_id", "sequence", "storage_key", "checksum", "size", "content_type")
            if any(getattr(existing, field) != getattr(frame, field) for field in fields):
                raise ValueError("replay frame conflicts with existing state evidence")
            return self._replay_frame_record(existing)
        model = VisualReplayFrameModel(
            id=frame.id, tenant_id=frame.tenant_id, session_id=frame.session_id,
            state_id=frame.state_id, sequence=frame.sequence, storage_key=frame.storage_key,
            checksum=frame.checksum, size=frame.size, content_type=frame.content_type,
            captured_at=frame.captured_at, deleted_at=frame.deleted_at,
        )
        self._session.add(model)
        self._session.flush()
        return self._replay_frame_record(model)

    def get_replay_frame(
        self, tenant_id: str, session_id: UUID, frame_id: UUID
    ) -> VisualReplayFrameRecord | None:
        model = self._session.scalar(
            select(VisualReplayFrameModel).where(
                VisualReplayFrameModel.tenant_id == tenant_id,
                VisualReplayFrameModel.session_id == session_id,
                VisualReplayFrameModel.id == frame_id,
                VisualReplayFrameModel.deleted_at.is_(None),
            )
        )
        return self._replay_frame_record(model) if model is not None else None

    def list_replay_frames(
        self, tenant_id: str, session_id: UUID
    ) -> list[VisualReplayFrameRecord]:
        models = self._session.scalars(
            select(VisualReplayFrameModel)
            .where(
                VisualReplayFrameModel.tenant_id == tenant_id,
                VisualReplayFrameModel.session_id == session_id,
                VisualReplayFrameModel.deleted_at.is_(None),
            )
            .order_by(VisualReplayFrameModel.sequence, VisualReplayFrameModel.id)
        )
        return [self._replay_frame_record(model) for model in models]

    def delete_replay_frame(self, tenant_id: str, session_id: UUID, frame_id: UUID) -> bool:
        result = self._session.execute(
            update(VisualReplayFrameModel)
            .where(
                VisualReplayFrameModel.tenant_id == tenant_id,
                VisualReplayFrameModel.session_id == session_id,
                VisualReplayFrameModel.id == frame_id,
                VisualReplayFrameModel.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now().astimezone())
        )
        return bool(result.rowcount)

    def delete_replay_frames(self, tenant_id: str, session_id: UUID) -> int:
        result = self._session.execute(
            update(VisualReplayFrameModel)
            .where(
                VisualReplayFrameModel.tenant_id == tenant_id,
                VisualReplayFrameModel.session_id == session_id,
                VisualReplayFrameModel.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now().astimezone())
        )
        return result.rowcount or 0

    @staticmethod
    def _trajectory_edge_record(model: VisualTrajectoryEdgeModel) -> VisualTrajectoryEdgeRecord:
        return VisualTrajectoryEdgeRecord(
            id=model.id, tenant_id=model.tenant_id, session_id=model.session_id,
            parent_state_id=model.parent_state_id, proposal_id=model.proposal_id,
            attempt=model.attempt, action=model.action, confidence=model.confidence,
            status=model.status, outcome_code=model.outcome_code,
            child_state_id=model.child_state_id, observed_at=model.observed_at,
            duration_ms=model.duration_ms, url_fingerprint=model.url_fingerprint,
            url_change=model.url_change, child_screenshot_checksum=model.child_screenshot_checksum,
            created_at=model.created_at,
        )

    def add_trajectory_edge(self, edge: VisualTrajectoryEdgeRecord) -> VisualTrajectoryEdgeRecord:
        """Insert an edge, then permit its single proposed-to-terminal finalization."""
        existing = self._session.scalar(
            select(VisualTrajectoryEdgeModel).where(
                VisualTrajectoryEdgeModel.session_id == edge.session_id,
                VisualTrajectoryEdgeModel.proposal_id == edge.proposal_id,
                VisualTrajectoryEdgeModel.attempt == edge.attempt,
            )
        )
        if existing is not None:
            identity_fields = ("tenant_id", "parent_state_id", "action", "confidence")
            if any(getattr(existing, field) != getattr(edge, field) for field in identity_fields):
                raise ValueError("trajectory edge conflicts with immutable proposal attempt")
            outcome_fields = (
                "status", "outcome_code", "child_state_id", "observed_at", "duration_ms",
                "url_fingerprint", "url_change", "child_screenshot_checksum",
            )
            if all(getattr(existing, field) == getattr(edge, field) for field in outcome_fields):
                return self._trajectory_edge_record(existing)
            if existing.status != "proposed" or edge.status == "proposed":
                raise ValueError("trajectory edge conflicts with immutable proposal attempt")
            for field in outcome_fields:
                setattr(existing, field, getattr(edge, field))
            self._session.flush()
            return self._trajectory_edge_record(existing)
        model = VisualTrajectoryEdgeModel(
            id=edge.id, tenant_id=edge.tenant_id, session_id=edge.session_id,
            parent_state_id=edge.parent_state_id, proposal_id=edge.proposal_id,
            attempt=edge.attempt, action=edge.action, confidence=edge.confidence,
            status=edge.status,
            outcome_code=edge.outcome_code, child_state_id=edge.child_state_id,
            observed_at=edge.observed_at, duration_ms=edge.duration_ms,
            url_fingerprint=edge.url_fingerprint, url_change=edge.url_change,
            child_screenshot_checksum=edge.child_screenshot_checksum, created_at=edge.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return self._trajectory_edge_record(model)

    def list_trajectory_edges(
        self, tenant_id: str, session_id: UUID
    ) -> list[VisualTrajectoryEdgeRecord]:
        models = self._session.scalars(
            select(VisualTrajectoryEdgeModel)
            .join(
                VisualActionProposalModel,
                VisualTrajectoryEdgeModel.proposal_id == VisualActionProposalModel.id,
            )
            .join(
                VisualExplorationStateModel,
                VisualTrajectoryEdgeModel.parent_state_id == VisualExplorationStateModel.id,
            )
            .where(
                VisualTrajectoryEdgeModel.tenant_id == tenant_id,
                VisualTrajectoryEdgeModel.session_id == session_id,
            )
            .order_by(
                VisualExplorationStateModel.created_at,
                VisualActionProposalModel.sequence,
                VisualTrajectoryEdgeModel.id,
            )
        )
        return [self._trajectory_edge_record(model) for model in models]

    def list_trajectory_edges_for_state(
        self, tenant_id: str, session_id: UUID, state_id: UUID
    ) -> list[VisualTrajectoryEdgeRecord]:
        return [
            edge
            for edge in self.list_trajectory_edges(tenant_id, session_id)
            if edge.parent_state_id == state_id or edge.child_state_id == state_id
        ]

    def add_action(self, proposal: VisualActionProposalModel) -> None:
        self._session.add(proposal)
        self._session.flush()

    def add_state(self, state: VisualExplorationStateModel) -> None:
        self._session.add(state)
        self._session.flush()

    def list_states(self, tenant_id: str, session_id: UUID) -> list[VisualExplorationStateModel]:
        return list(self._session.scalars(
            select(VisualExplorationStateModel).where(
                VisualExplorationStateModel.tenant_id == tenant_id,
                VisualExplorationStateModel.session_id == session_id,
            ).order_by(VisualExplorationStateModel.created_at, VisualExplorationStateModel.id)
        ))

    def list_actions(self, tenant_id: str, session_id: UUID) -> list[VisualActionProposalModel]:
        return list(
            self._session.scalars(
                select(VisualActionProposalModel)
                .where(
                    VisualActionProposalModel.tenant_id == tenant_id,
                    VisualActionProposalModel.session_id == session_id,
                )
                .order_by(VisualActionProposalModel.sequence)
            )
        )

    def add_debug_evidence(self, evidence: VisionDebugEvidenceModel) -> VisionDebugEvidenceModel:
        """Insert once per state/attempt; duplicate at-least-once delivery is harmless."""
        existing = self._session.scalar(
            select(VisionDebugEvidenceModel).where(
                VisionDebugEvidenceModel.session_id == evidence.session_id,
                VisionDebugEvidenceModel.state_id == evidence.state_id,
                VisionDebugEvidenceModel.attempt_key == evidence.attempt_key,
            )
        )
        if existing is not None:
            return existing
        self._session.add(evidence)
        self._session.flush()
        return evidence

    def list_debug_evidence_metadata(
        self, tenant_id: str, session_id: UUID
    ) -> list[VisionDebugEvidenceModel]:
        return list(
            self._session.scalars(
                select(VisionDebugEvidenceModel)
                .where(
                    VisionDebugEvidenceModel.tenant_id == tenant_id,
                    VisionDebugEvidenceModel.session_id == session_id,
                    VisionDebugEvidenceModel.deleted_at.is_(None),
                )
                .order_by(VisionDebugEvidenceModel.captured_at, VisionDebugEvidenceModel.id)
            )
        )

    def get_debug_evidence(
        self, tenant_id: str, evidence_id: UUID
    ) -> VisionDebugEvidenceModel | None:
        return self._session.scalar(
            select(VisionDebugEvidenceModel).where(
                VisionDebugEvidenceModel.tenant_id == tenant_id,
                VisionDebugEvidenceModel.id == evidence_id,
                VisionDebugEvidenceModel.deleted_at.is_(None),
            )
        )

    def list_expired_debug_evidence(
        self, before: datetime, limit: int
    ) -> list[VisionDebugEvidenceModel]:
        return list(
            self._session.scalars(
                select(VisionDebugEvidenceModel)
                .where(
                    VisionDebugEvidenceModel.retention_until <= before,
                    VisionDebugEvidenceModel.deleted_at.is_(None),
                )
                .order_by(VisionDebugEvidenceModel.retention_until, VisionDebugEvidenceModel.id)
                .limit(limit)
            )
        )

    def delete_expired_debug_evidence(self, tenant_id: str, evidence_id: UUID) -> bool:
        result = self._session.execute(
            VisionDebugEvidenceModel.__table__.delete().where(
                VisionDebugEvidenceModel.tenant_id == tenant_id,
                VisionDebugEvidenceModel.id == evidence_id,
                VisionDebugEvidenceModel.retention_until <= datetime.now().astimezone(),
            )
        )
        return bool(result.rowcount)
