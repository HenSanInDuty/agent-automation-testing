"""Tenant-scoped SQLAlchemy implementations of domain persistence ports."""

from uuid import UUID

from auto_at.contracts.execution import TestExecutionResult
from domain.entities import ArtifactRecord
from domain.runs import AuditEvent, OutboxEvent, RunLifecycleStatus, TestRun
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from infrastructure.persistence.models import (
    ArtifactModel,
    AuditEventModel,
    OutboxEventModel,
    TestRunModel,
)


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
        if self._session.execute(statement).rowcount != 1:
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
                id=artifact.id, tenant_id=artifact.tenant_id, run_id=artifact.run_id,
                kind=artifact.kind, uri=artifact.uri, checksum=artifact.checksum,
                size=artifact.size, content_type=artifact.content_type,
                retention_until=artifact.retention_until,
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
