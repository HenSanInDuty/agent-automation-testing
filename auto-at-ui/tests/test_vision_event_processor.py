import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from application.vision_events import VisionEventProcessor
from config import Settings
from domain.runs import OutboxEvent


class Sessions:
    def __init__(self, session):
        self.session = session

    def get(self, tenant_id, session_id):
        return self.session

    def add_action(self, proposal):
        raise AssertionError("terminal session must not add an action")


class Configs:
    def get(self, tenant_id, key):
        return None


class Events:
    def __init__(self):
        self.items = []

    def append(self, event):
        self.items.append(event)


def event(session):
    return OutboxEvent(
        id=uuid4(),
        tenant_id=session.tenant_id,
        event_type="agent.visual_exploration.requested.v1",
        schema_version="v1",
        correlation_id=session.correlation_id,
        causation_id=None,
        idempotency_key="vision:x",
        payload={"session_id": str(session.id)},
    )


def test_terminal_visual_session_is_idempotent_without_model_or_worker_calls():
    session = SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        correlation_id=uuid4(),
        state="completed",
        project_id=uuid4(),
        encrypted_task_intent="",
        intent_retention_until=datetime.now(UTC) + timedelta(days=1),
    )
    events = Events()
    processor = VisionEventProcessor(
        Sessions(session), Configs(), object(), events, events, events, Settings()
    )

    assert asyncio.run(processor.execute(event(session))) == "already_processed"
    assert events.items == []
