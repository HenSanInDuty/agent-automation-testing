"""Use cases for the deterministic test-run lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from auto_at.contracts.events import EventType
from auto_at.contracts.execution import (
    ArtifactPolicy,
    RunStatus,
    TargetType,
    TestExecutionRequest,
    TestExecutionResult,
)
from domain.activity import ActivityEvent
from domain.entities import ArtifactRecord
from domain.ports import (
    ActivityEventRepository,
    ArtifactRepository,
    AuditEventRepository,
    OutboxEventRepository,
    RunnerTransport,
    RunRepository,
    TriageEventHandler,
    WorkflowStarter,
)
from domain.runs import TERMINAL_STATUSES, AuditEvent, OutboxEvent, TestRun
from pydantic import HttpUrl


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
    target_type: TargetType = TargetType.WEB_UI
    target_url: str | None = None
    runner_config: dict[str, object] | None = None
    artifact_policy: ArtifactPolicy | None = None


class CreateRun:
    """Create a queued run and its requested event through shared repositories."""

    def __init__(
        self,
        runs: RunRepository,
        outbox: OutboxEventRepository,
        audits: AuditEventRepository,
        activities: ActivityEventRepository | None = None,
    ) -> None:
        self._runs = runs
        self._outbox = outbox
        self._audits = audits
        self._activities = activities

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
        request = TestExecutionRequest(
            run_id=run.id,
            correlation_id=run.correlation_id,
            project_id=run.project_id,
            test_case_id=run.test_case_id,
            target_type=command.target_type,
            target_url=HttpUrl(command.target_url) if command.target_url else None,
            revision=run.revision,
            runner_config=command.runner_config or {},
            artifact_policy=command.artifact_policy or ArtifactPolicy(),
        )
        run.request = request
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
        if self._activities is not None:
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=command.tenant_id,
                    run_id=run.id,
                    correlation_id=run.correlation_id,
                    source="control_plane",
                    stage="run.created",
                    status="queued",
                    safe_summary="Run queued for durable dispatch.",
                    occurred_at=datetime.now(UTC),
                )
            )
            steps = request.runner_config.get("steps")
            if isinstance(steps, list):
                for index, _ in enumerate(steps, start=1):
                    self._activities.append(
                        ActivityEvent.create(
                            tenant_id=command.tenant_id,
                            run_id=run.id,
                            correlation_id=run.correlation_id,
                            source="control_plane",
                            stage=f"browser.todo.{index}",
                            status="queued",
                            safe_summary=f"Browser todo step {index} queued.",
                            occurred_at=datetime.now(UTC),
                            metadata={"step_index": index},
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
                payload={
                    "run_id": str(run.id),
                    "request": request.model_dump(mode="json"),
                    "requested_at": datetime.now(UTC).isoformat(),
                },
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
        if run.status in TERMINAL_STATUSES:
            if run.result == result:
                return run
            raise ValueError("a terminal run cannot receive a different result")
        self._runs.save_result(run, result)
        return run


class RequestFailureTriage:
    """Queue advisory triage after an observed failure without mutating its verdict."""

    def __init__(
        self,
        outbox: OutboxEventRepository,
        audits: AuditEventRepository,
        activities: ActivityEventRepository | None = None,
    ) -> None:
        self._outbox = outbox
        self._audits = audits
        self._activities = activities

    def execute(self, run: TestRun) -> None:
        if run.result is None or run.result.status not in {
            RunStatus.FAILED,
            RunStatus.ERRORED,
        }:
            return
        idempotency_key = f"triage:{run.id}:v1"
        if self._outbox.get_by_idempotency_key(run.tenant_id, idempotency_key) is not None:
            return
        event = OutboxEvent(
            id=uuid4(),
            tenant_id=run.tenant_id,
            event_type=EventType.AGENT_TRIAGE_REQUESTED.value,
            schema_version="v1",
            correlation_id=run.correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            payload={"run_id": str(run.id)},
        )
        self._outbox.append(event)
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=run.tenant_id,
                actor="system",
                action="triage.requested",
                entity_type="test_run",
                entity_id=run.id,
                correlation_id=run.correlation_id,
            )
        )
        if self._activities is not None:
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    correlation_id=run.correlation_id,
                    source="triage",
                    stage="requested",
                    status="queued",
                    safe_summary="Failure triage was queued.",
                    occurred_at=datetime.now(UTC),
                )
            )


class RequestRunReport:
    """Queue one read-only report for every result-bearing terminal run."""

    def __init__(
        self,
        outbox: OutboxEventRepository,
        audits: AuditEventRepository,
        activities: ActivityEventRepository | None = None,
    ) -> None:
        self._outbox = outbox
        self._audits = audits
        self._activities = activities

    def execute(self, run: TestRun) -> None:
        if run.result is None or run.result.status not in {
            RunStatus.PASSED,
            RunStatus.FAILED,
            RunStatus.ERRORED,
            RunStatus.SKIPPED,
        }:
            return
        idempotency_key = f"run-report:{run.id}:v1"
        if self._outbox.get_by_idempotency_key(run.tenant_id, idempotency_key) is not None:
            return
        self._outbox.append(
            OutboxEvent(
                id=uuid4(),
                tenant_id=run.tenant_id,
                event_type=EventType.AGENT_RUN_REPORT_REQUESTED.value,
                schema_version="v1",
                correlation_id=run.correlation_id,
                causation_id=None,
                idempotency_key=idempotency_key,
                payload={"run_id": str(run.id)},
            )
        )
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=run.tenant_id,
                actor="system",
                action="run_report.requested",
                entity_type="test_run",
                entity_id=run.id,
                correlation_id=run.correlation_id,
            )
        )
        if self._activities is not None:
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    correlation_id=run.correlation_id,
                    source="reporting",
                    stage="requested",
                    status="queued",
                    safe_summary="AI post-run review queued.",
                    occurred_at=datetime.now(UTC),
                )
            )


class CancelRun:
    """Persist cancellation before asking the workflow plane to stop execution."""

    def __init__(
        self,
        runs: RunRepository,
        outbox: OutboxEventRepository,
        audits: AuditEventRepository,
        activities: ActivityEventRepository | None = None,
    ) -> None:
        self._runs = runs
        self._outbox = outbox
        self._audits = audits
        self._activities = activities

    def execute(self, tenant_id: str, run_id: UUID, idempotency_key: str) -> TestRun:
        existing = self._outbox.get_by_idempotency_key(tenant_id, idempotency_key)
        if existing is not None:
            if existing.event_type != EventType.TEST_RUN_CANCELLED.value:
                raise IdempotencyConflictError("idempotency key belongs to another command")
            return GetRun(self._runs).execute(tenant_id, run_id)

        run = GetRun(self._runs).execute(tenant_id, run_id)
        self._runs.cancel(run)
        event = OutboxEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            event_type=EventType.TEST_RUN_CANCELLED.value,
            schema_version="v1",
            correlation_id=run.correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            payload={"run_id": str(run.id)},
        )
        self._outbox.append(event)
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor="system",
                action="run.cancelled",
                entity_type="test_run",
                entity_id=run.id,
                correlation_id=run.correlation_id,
            )
        )
        if self._activities is not None:
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    correlation_id=run.correlation_id,
                    source="control_plane",
                    stage="run.cancelled",
                    status="cancelled",
                    safe_summary="Run cancellation was requested.",
                    occurred_at=datetime.now(UTC),
                )
            )
        return run


class DispatchRun:
    """Dispatch through a port; the worker remains the sole terminal verdict authority."""

    def __init__(self, runs: RunRepository, transport: RunnerTransport) -> None:
        self._runs = runs
        self._transport = transport

    def execute(
        self,
        tenant_id: str,
        request: TestExecutionRequest,
    ) -> tuple[TestRun, TestExecutionResult]:
        run = GetRun(self._runs).execute(tenant_id, request.run_id)
        if run.status in TERMINAL_STATUSES:
            raise ValueError("a terminal run cannot be dispatched")
        if request.correlation_id != run.correlation_id:
            raise ValueError("request correlation_id does not match the queued run")
        if request.project_id != run.project_id or request.revision != run.revision:
            raise ValueError("request does not match the queued run")
        result = self._transport.execute(request)
        return run, result


class PublishOutbox:
    """Publish committed run events. The backend supplies at-least-once delivery."""

    def __init__(
        self,
        outbox: OutboxEventRepository,
        workflows: WorkflowStarter,
        triage: TriageEventHandler | None = None,
        generation: TriageEventHandler | None = None,
        reporting: TriageEventHandler | None = None,
        vision: TriageEventHandler | None = None,
    ) -> None:
        self._outbox = outbox
        self._workflows = workflows
        self._triage = triage
        self._generation = generation
        self._reporting = reporting
        self._vision = vision

    async def execute(self, limit: int = 100) -> int:
        published = 0
        event_order = {
            EventType.TEST_RUN_REQUESTED.value: 0,
            EventType.TEST_RUN_CANCELLED.value: 1,
        }
        events = sorted(
            self._outbox.list_unpublished(limit),
            key=lambda event: event_order.get(event.event_type, 2),
        )
        for event in events:
            if event.event_type == EventType.TEST_RUN_REQUESTED.value:
                await self._workflows.start_run(event)
            elif event.event_type == EventType.TEST_RUN_CANCELLED.value:
                await self._workflows.cancel_run(event)
            elif (
                event.event_type == EventType.AGENT_TRIAGE_REQUESTED.value
                and self._triage is not None
            ):
                await self._triage.execute(event)
            elif (
                event.event_type == "agent.test_generation.requested.v1"
                and self._generation is not None
            ):
                await self._generation.execute(event)
            elif (
                event.event_type == EventType.AGENT_RUN_REPORT_REQUESTED.value
                and self._reporting is not None
            ):
                await self._reporting.execute(event)
            elif (
                event.event_type == "agent.visual_exploration.requested.v1"
                and self._vision is not None
            ):
                await self._vision.execute(event)
            else:
                continue
            self._outbox.mark_published(event.id, datetime.now(UTC))
            published += 1
        return published
