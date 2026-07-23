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

    async def start_run(self, event: OutboxEvent) -> None:
        self.started.append(event)


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
