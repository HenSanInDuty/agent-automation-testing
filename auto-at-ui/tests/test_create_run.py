from uuid import UUID, uuid4

from application.runs import CreateRun, CreateRunCommand
from domain.runs import AuditEvent, OutboxEvent
from domain.runs import TestRun as DomainTestRun


class InMemoryRuns:
    def __init__(self) -> None:
        self.runs: dict[UUID, DomainTestRun] = {}

    def get(self, tenant_id: str, run_id: UUID) -> DomainTestRun | None:
        run = self.runs.get(run_id)
        return run if run is not None and run.tenant_id == tenant_id else None

    def add(self, run: DomainTestRun) -> None:
        self.runs[run.id] = run


class InMemoryOutbox:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str], OutboxEvent] = {}

    def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> OutboxEvent | None:
        return self.events.get((tenant_id, idempotency_key))

    def append(self, event: OutboxEvent) -> None:
        self.events[(event.tenant_id, event.idempotency_key)] = event


class InMemoryAudits:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)


def command() -> CreateRunCommand:
    return CreateRunCommand(
        tenant_id="tenant-a",
        project_id=uuid4(),
        test_case_id="checkout",
        revision="a" * 40,
        correlation_id=uuid4(),
        idempotency_key="checkout:request:1",
    )


def test_create_run_queues_a_run_and_outbox_event() -> None:
    runs = InMemoryRuns()
    outbox = InMemoryOutbox()
    audits = InMemoryAudits()

    run = CreateRun(runs, outbox, audits).execute(command())

    assert runs.get("tenant-a", run.id) == run
    assert len(outbox.events) == 1
    event = next(iter(outbox.events.values()))
    assert event.event_type == "test.run.requested.v1"
    assert event.payload["run_id"] == str(run.id)
    assert event.payload["request"]["run_id"] == str(run.id)
    assert event.payload["request"]["correlation_id"] == str(run.correlation_id)
    assert audits.events[0].action == "run.created"


def test_repeated_idempotency_key_returns_the_original_run() -> None:
    runs = InMemoryRuns()
    outbox = InMemoryOutbox()
    audits = InMemoryAudits()
    use_case = CreateRun(runs, outbox, audits)
    first = use_case.execute(command())
    duplicate = use_case.execute(command())

    assert duplicate == first
    assert len(runs.runs) == 1
    assert len(outbox.events) == 1
    assert len(audits.events) == 1
