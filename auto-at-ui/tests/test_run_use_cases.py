from uuid import UUID, uuid4

import pytest
from application.runs import (
    CancelRun,
    GetRun,
    ListArtifacts,
    RecordDeterministicResult,
    RequestFailureTriage,
    RunNotFoundError,
)
from auto_at.contracts.execution import RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from domain.entities import ArtifactRecord
from domain.runs import OutboxEvent
from domain.runs import TestRun as DomainTestRun


class InMemoryRuns:
    def __init__(self, run: DomainTestRun) -> None:
        self.run = run

    def get(self, tenant_id: str, run_id: UUID) -> DomainTestRun | None:
        if self.run.tenant_id == tenant_id and self.run.id == run_id:
            return self.run
        return None

    def save_result(self, run: DomainTestRun, result: ExecutionResult) -> None:
        run.record_runner_result(result)

    def cancel(self, run: DomainTestRun) -> None:
        run.cancel()


def make_run() -> DomainTestRun:
    return DomainTestRun.create(
        tenant_id="tenant-a",
        project_id=uuid4(),
        test_case_id="checkout",
        revision="a" * 40,
        correlation_id=uuid4(),
    )


def test_get_run_rejects_another_tenant() -> None:
    run = make_run()

    with pytest.raises(RunNotFoundError):
        GetRun(InMemoryRuns(run)).execute("tenant-b", run.id)


def test_record_result_uses_the_runner_contract() -> None:
    run = make_run()
    result = ExecutionResult(
        run_id=run.id,
        correlation_id=run.correlation_id,
        status=RunStatus.PASSED,
        started_at="2026-07-21T09:00:00Z",
        completed_at="2026-07-21T09:01:00Z",
        summary="Passed.",
    )

    recorded = RecordDeterministicResult(InMemoryRuns(run)).execute("tenant-a", result)

    assert recorded.result == result
    assert recorded.status.value == "passed"


def test_recording_an_identical_terminal_result_is_idempotent() -> None:
    run = make_run()
    result = ExecutionResult(
        run_id=run.id,
        correlation_id=run.correlation_id,
        status=RunStatus.PASSED,
        started_at="2026-07-21T09:00:00Z",
        completed_at="2026-07-21T09:01:00Z",
        summary="Passed.",
    )
    use_case = RecordDeterministicResult(InMemoryRuns(run))

    first = use_case.execute("tenant-a", result)
    second = use_case.execute("tenant-a", result)

    assert first is second
    assert second.status.value == "passed"
    assert second.version == 2


def test_failed_run_queues_one_advisory_triage_event() -> None:
    class Outbox:
        def __init__(self) -> None:
            self.events: list[OutboxEvent] = []

        def get_by_idempotency_key(
            self, tenant_id: str, idempotency_key: str
        ) -> OutboxEvent | None:
            return next(
                (event for event in self.events if event.idempotency_key == idempotency_key), None
            )

        def append(self, event: OutboxEvent) -> None:
            self.events.append(event)

    class Audits:
        def __init__(self) -> None:
            self.events = []

        def append(self, event: object) -> None:
            self.events.append(event)

    run = make_run()
    result = ExecutionResult(
        run_id=run.id,
        correlation_id=run.correlation_id,
        status=RunStatus.FAILED,
        started_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:00:01Z",
        summary="Failed.",
    )
    RecordDeterministicResult(InMemoryRuns(run)).execute("tenant-a", result)
    outbox = Outbox()
    audits = Audits()
    use_case = RequestFailureTriage(outbox, audits)

    use_case.execute(run)
    use_case.execute(run)

    assert [event.event_type for event in outbox.events] == ["agent.triage.requested.v1"]
    assert len(audits.events) == 1


def test_list_artifacts_is_scoped_to_the_run_and_tenant() -> None:
    run = make_run()
    artifact = ArtifactRecord(
        id=uuid4(),
        tenant_id="tenant-a",
        run_id=run.id,
        kind="screenshot",
        uri="minio://artifacts/run.png",
        checksum="a" * 64,
        size=123,
    )

    class Artifacts:
        def list_for_run(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]:
            return [artifact] if (tenant_id, run_id) == ("tenant-a", run.id) else []

    assert ListArtifacts(Artifacts()).execute("tenant-a", run.id) == [artifact]
    assert ListArtifacts(Artifacts()).execute("tenant-b", run.id) == []


def test_cancel_run_persists_a_cancellation_delivery_command() -> None:
    run = make_run()

    class Outbox:
        def __init__(self) -> None:
            self.event = None

        def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str):
            return None

        def append(self, event) -> None:
            self.event = event

    class Audits:
        def __init__(self) -> None:
            self.events = []

        def append(self, event) -> None:
            self.events.append(event)

    outbox = Outbox()
    audits = Audits()
    cancelled = CancelRun(InMemoryRuns(run), outbox, audits).execute(
        "tenant-a", run.id, "cancel:checkout:1"
    )

    assert cancelled.status.value == "cancelled"
    assert outbox.event.event_type == "test.run.cancelled.v1"
    assert outbox.event.payload == {"run_id": str(run.id)}
    assert audits.events[0].action == "run.cancelled"
