"""Pure lifecycle rules for deterministic test runs."""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

from auto_at.contracts.execution import TestExecutionResult


class RunStateError(ValueError):
    """Raised when an operation would violate a test-run lifecycle invariant."""


class RunLifecycleStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {
        RunLifecycleStatus.PASSED,
        RunLifecycleStatus.FAILED,
        RunLifecycleStatus.ERRORED,
        RunLifecycleStatus.SKIPPED,
        RunLifecycleStatus.CANCELLED,
    }
)


@dataclass
class TestRun:
    """A run's business state; only an observed runner result sets its verdict."""

    id: UUID
    tenant_id: str
    project_id: UUID
    test_case_id: str
    revision: str
    correlation_id: UUID
    status: RunLifecycleStatus = RunLifecycleStatus.QUEUED
    result: TestExecutionResult | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        project_id: UUID,
        test_case_id: str,
        revision: str,
        correlation_id: UUID,
    ) -> "TestRun":
        if not tenant_id:
            raise RunStateError("tenant_id is required")
        if not test_case_id:
            raise RunStateError("test_case_id is required")
        if len(revision) < 7:
            raise RunStateError("revision must identify an immutable source version")
        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            test_case_id=test_case_id,
            revision=revision,
            correlation_id=correlation_id,
        )

    def change_revision(self, revision: str) -> None:
        """Deliberately reject revision mutation after a run has been created."""
        raise RunStateError("run revision is immutable")

    def record_runner_result(self, result: TestExecutionResult) -> None:
        """Persist the terminal observation emitted by the deterministic runner."""
        if self.status in TERMINAL_STATUSES:
            raise RunStateError("a terminal run cannot receive another result")
        if result.run_id != self.id:
            raise RunStateError("runner result run_id does not match this run")
        if result.correlation_id != self.correlation_id:
            raise RunStateError("runner result correlation_id does not match this run")

        self.result = result
        self.status = RunLifecycleStatus(result.status.value)
        self.version += 1

    def cancel(self) -> None:
        """Stop a run without inventing a runner verdict."""
        if self.status in TERMINAL_STATUSES:
            raise RunStateError("a terminal run cannot be cancelled")
        self.status = RunLifecycleStatus.CANCELLED
        self.version += 1


@dataclass(frozen=True)
class AuditEvent:
    """An append-only record of a business action."""

    id: UUID
    tenant_id: str
    actor: str
    action: str
    entity_type: str
    entity_id: UUID
    correlation_id: UUID
    before_hash: str | None = None
    after_hash: str | None = None


@dataclass(frozen=True)
class OutboxEvent:
    """An event committed alongside a business state transition."""

    id: UUID
    tenant_id: str
    event_type: str
    schema_version: str
    correlation_id: UUID
    causation_id: UUID | None
    idempotency_key: str
    payload: dict[str, object] = field(default_factory=dict)
