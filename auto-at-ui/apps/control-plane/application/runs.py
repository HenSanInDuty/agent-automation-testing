"""Use cases for the deterministic test-run lifecycle."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from auto_at.contracts.events import EventType
from auto_at.contracts.execution import TestExecutionResult
from domain.entities import ArtifactRecord
from domain.ports import (
    ArtifactRepository,
    AuditEventRepository,
    OutboxEventRepository,
    RunRepository,
)
from domain.runs import AuditEvent, OutboxEvent, TestRun


class IdempotencyConflictError(ValueError):
    """Raised when an existing key belongs to a missing run record."""


class RunNotFoundError(LookupError):
    """Raised when a tenant cannot access the requested run."""


@dataclass(frozen=True)
class CreateRunCommand:
    tenant_id: str
    project_id: UUID
    test_case_id: str
    revision: str
    correlation_id: UUID
    idempotency_key: str


class CreateRun:
    """Create a queued run and its requested event through shared repositories."""

    def __init__(
        self,
        runs: RunRepository,
        outbox: OutboxEventRepository,
        audits: AuditEventRepository,
    ) -> None:
        self._runs = runs
        self._outbox = outbox
        self._audits = audits

    def execute(self, command: CreateRunCommand) -> TestRun:
        existing_event = self._outbox.get_by_idempotency_key(
            command.tenant_id, command.idempotency_key
        )
        if existing_event is not None:
            run_id = UUID(str(existing_event.payload["run_id"]))
            existing_run = self._runs.get(command.tenant_id, run_id)
            if existing_run is None:
                raise IdempotencyConflictError("idempotency key refers to a missing run")
            return existing_run

        run = TestRun.create(
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            test_case_id=command.test_case_id,
            revision=command.revision,
            correlation_id=command.correlation_id,
        )
        self._runs.add(run)
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=command.tenant_id,
                actor="system",
                action="run.created",
                entity_type="test_run",
                entity_id=run.id,
                correlation_id=command.correlation_id,
            )
        )
        self._outbox.append(
            OutboxEvent(
                id=uuid4(),
                tenant_id=command.tenant_id,
                event_type=EventType.TEST_RUN_REQUESTED.value,
                schema_version="v1",
                correlation_id=command.correlation_id,
                causation_id=None,
                idempotency_key=command.idempotency_key,
                payload={"run_id": str(run.id)},
            )
        )
        return run


class GetRun:
    def __init__(self, runs: RunRepository) -> None:
        self._runs = runs

    def execute(self, tenant_id: str, run_id: UUID) -> TestRun:
        run = self._runs.get(tenant_id, run_id)
        if run is None:
            raise RunNotFoundError("test run was not found")
        return run


class ListArtifacts:
    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    def execute(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]:
        return self._artifacts.list_for_run(tenant_id, run_id)


class RecordDeterministicResult:
    def __init__(self, runs: RunRepository) -> None:
        self._runs = runs

    def execute(self, tenant_id: str, result: TestExecutionResult) -> TestRun:
        run = GetRun(self._runs).execute(tenant_id, result.run_id)
        self._runs.save_result(run, result)
        return run
