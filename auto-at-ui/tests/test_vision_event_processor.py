import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from agents.vision.diagnostics import VisualDiagnosticCapture, VisualDiagnosticCode
from agents.vision.executor import VisualCandidateBatchOutcome
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

    def add_debug_evidence(self, evidence):
        self.debug_evidence = evidence
        return evidence


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


def test_rejected_batch_capture_is_encrypted_audited_and_never_leaks_model_text():
    session = SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        correlation_id=uuid4(),
        provider="huggingface",
        model="approved-model",
        prompt_version="vision-exploration-v1",
    )
    sessions, events = Sessions(session), Events()
    settings = Settings().model_copy(
        update={
            "vision_debug_evidence_encryption_key": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            "vision_debug_evidence_key_id": "debug-v1",
        }
    )
    processor = VisionEventProcessor(
        sessions, Configs(), object(), events, events, events, settings
    )
    outcome = VisualCandidateBatchOutcome(
        status="unavailable",
        detail="vision model returned an invalid candidate batch",
        diagnostic_code=VisualDiagnosticCode.INVALID_JSON,
        diagnostic_capture=VisualDiagnosticCapture.from_content("token=sentinel-secret"),
    )

    processor._capture_rejected_batch(
        session=session, state_id=uuid4(), attempt_key="state:1:approved-model", outcome=outcome
    )

    assert sessions.debug_evidence.diagnostic_code == "invalid_json"
    assert "sentinel-secret" not in sessions.debug_evidence.encrypted_payload
    assert all("sentinel-secret" not in str(item) for item in events.items)
    assert any(
        getattr(item, "action", None) == "vision.debug_evidence_captured"
        for item in events.items
    )
