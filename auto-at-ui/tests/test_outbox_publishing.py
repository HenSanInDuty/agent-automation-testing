import asyncio
from datetime import datetime
from uuid import uuid4

from application.runs import PublishOutbox
from domain.runs import OutboxEvent


class InMemoryOutbox:
    def __init__(self, events: list[OutboxEvent]) -> None:
        self.events = events
        self.published: dict[object, datetime] = {}

    def list_unpublished(self, limit: int) -> list[OutboxEvent]:
        return [event for event in self.events if event.id not in self.published][:limit]

    def mark_published(self, event_id: object, published_at: datetime) -> None:
        self.published[event_id] = published_at


class RecordingWorkflowStarter:
    def __init__(self) -> None:
        self.started: list[OutboxEvent] = []
        self.cancelled: list[OutboxEvent] = []

    async def start_run(self, event: OutboxEvent) -> None:
        self.started.append(event)

    async def cancel_run(self, event: OutboxEvent) -> None:
        self.cancelled.append(event)


class RecordingTriageHandler:
    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    async def execute(self, event: OutboxEvent) -> None:
        self.events.append(event)


class RecordingGenerationHandler(RecordingTriageHandler):
    pass


class RecordingReportingHandler(RecordingTriageHandler):
    pass


def requested_event() -> OutboxEvent:
    run_id = uuid4()
    return OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="test.run.requested.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="run:one",
        payload={"run_id": str(run_id), "request": {"run_id": str(run_id)}},
    )


def test_publisher_starts_and_marks_each_requested_run_once() -> None:
    event = requested_event()
    outbox = InMemoryOutbox([event])
    workflows = RecordingWorkflowStarter()

    assert asyncio.run(PublishOutbox(outbox, workflows).execute()) == 1
    assert workflows.started == [event]
    assert event.id in outbox.published

    assert asyncio.run(PublishOutbox(outbox, workflows).execute()) == 0
    assert workflows.started == [event]


def test_publisher_leaves_other_event_types_unpublished() -> None:
    event = requested_event()
    ignored = OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="agent.triage.requested.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="triage:one",
    )
    outbox = InMemoryOutbox([ignored, event])
    workflows = RecordingWorkflowStarter()

    assert asyncio.run(PublishOutbox(outbox, workflows).execute()) == 1
    assert workflows.started == [event]
    assert ignored.id not in outbox.published
    assert event.id in outbox.published


def test_publisher_delivers_triage_events_when_a_triage_handler_is_configured() -> None:
    event = OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="agent.triage.requested.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="triage:one",
        payload={"run_id": str(uuid4())},
    )
    outbox = InMemoryOutbox([event])
    workflows = RecordingWorkflowStarter()
    triage = RecordingTriageHandler()

    assert asyncio.run(PublishOutbox(outbox, workflows, triage).execute()) == 1
    assert triage.events == [event]
    assert event.id in outbox.published
    assert asyncio.run(PublishOutbox(outbox, workflows, triage).execute()) == 0


def test_publisher_delivers_a_run_cancellation_once() -> None:
    event = requested_event()
    event = OutboxEvent(
        id=event.id,
        tenant_id=event.tenant_id,
        event_type="test.run.cancelled.v1",
        schema_version=event.schema_version,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        idempotency_key="cancel:one",
        payload={"run_id": event.payload["run_id"]},
    )
    outbox = InMemoryOutbox([event])
    workflows = RecordingWorkflowStarter()

    assert asyncio.run(PublishOutbox(outbox, workflows).execute()) == 1
    assert workflows.cancelled == [event]
    assert event.id in outbox.published


def test_publisher_delivers_generation_events_only_when_a_handler_is_configured() -> None:
    event = OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="agent.test_generation.requested.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="generation:one",
        payload={"request_id": str(uuid4())},
    )
    outbox = InMemoryOutbox([event])
    handler = RecordingGenerationHandler()

    assert asyncio.run(PublishOutbox(outbox, RecordingWorkflowStarter()).execute()) == 0
    publisher = PublishOutbox(outbox, RecordingWorkflowStarter(), generation=handler)
    assert asyncio.run(publisher.execute()) == 1
    assert handler.events == [event]


def test_publisher_delivers_reporting_events_only_when_a_handler_is_configured() -> None:
    event = OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="agent.run_report.requested.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="run-report:one",
        payload={"run_id": str(uuid4())},
    )
    outbox = InMemoryOutbox([event])
    handler = RecordingReportingHandler()

    assert asyncio.run(PublishOutbox(outbox, RecordingWorkflowStarter()).execute()) == 0
    publisher = PublishOutbox(outbox, RecordingWorkflowStarter(), reporting=handler)
    assert asyncio.run(publisher.execute()) == 1
    assert handler.events == [event]


def test_publisher_starts_a_run_before_delivering_its_cancellation() -> None:
    requested = requested_event()
    cancelled = OutboxEvent(
        id=uuid4(),
        tenant_id=requested.tenant_id,
        event_type="test.run.cancelled.v1",
        schema_version=requested.schema_version,
        correlation_id=requested.correlation_id,
        causation_id=None,
        idempotency_key="cancel:after-start",
        payload={"run_id": requested.payload["run_id"]},
    )
    outbox = InMemoryOutbox([cancelled, requested])
    workflows = RecordingWorkflowStarter()

    assert asyncio.run(PublishOutbox(outbox, workflows).execute()) == 2
    assert workflows.started == [requested]
    assert workflows.cancelled == [cancelled]
