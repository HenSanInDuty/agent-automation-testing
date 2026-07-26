import asyncio
from uuid import uuid4

from config import Settings
from domain.runs import OutboxEvent
from infrastructure.workflows.temporal import TemporalWorkflowStarter


class WorkflowHandle:
    def __init__(self) -> None:
        self.cancelled = False

    async def cancel(self) -> None:
        self.cancelled = True


class Client:
    def __init__(self) -> None:
        self.workflow_id: str | None = None
        self.handle = WorkflowHandle()

    def get_workflow_handle(self, workflow_id: str) -> WorkflowHandle:
        self.workflow_id = workflow_id
        return self.handle


class StartClient:
    def __init__(self) -> None:
        self.workflow_ids: list[str] = []

    async def start_workflow(self, *args, **kwargs) -> None:
        self.workflow_ids.append(kwargs["id"])
        if len(self.workflow_ids) > 1:
            raise DuplicateWorkflow()


class DuplicateWorkflow(Exception):
    pass


def test_temporal_cancellation_reaches_the_workflow_and_playwright_worker(monkeypatch) -> None:
    client = Client()
    notified: list[str] = []
    event = OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="test.run.cancelled.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="cancel:one",
        payload={"run_id": "run-1"},
    )
    monkeypatch.setattr(
        "infrastructure.workflows.temporal.HttpPlaywrightTransport.cancel",
        lambda self, run_id: notified.append(run_id),
    )

    asyncio.run(TemporalWorkflowStarter(client, Settings()).cancel_run(event))

    assert client.workflow_id == "auto-at-run-run-1"
    assert client.handle.cancelled is True
    assert notified == ["run-1"]


def test_duplicate_run_requests_share_one_stable_temporal_workflow(monkeypatch) -> None:
    client = StartClient()
    event = OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="test.run.requested.v1",
        schema_version="v1",
        correlation_id=uuid4(),
        causation_id=None,
        idempotency_key="run:one",
        payload={"run_id": "run-1", "request": {"run_id": "run-1"}},
    )
    monkeypatch.setattr(
        "infrastructure.workflows.temporal.WorkflowAlreadyStartedError", DuplicateWorkflow
    )
    starter = TemporalWorkflowStarter(client, Settings())

    asyncio.run(starter.start_run(event))
    asyncio.run(starter.start_run(event))

    assert client.workflow_ids == ["auto-at-run-run-1", "auto-at-run-run-1"]
