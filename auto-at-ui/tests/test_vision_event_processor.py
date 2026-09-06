import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from agents.vision.diagnostics import VisualDiagnosticCapture, VisualDiagnosticCode
from agents.vision.executor import VisualCandidateBatchOutcome
from application.vision_events import VisionEventProcessor
from auto_at.contracts.vision import VisualAction
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


class Generation:
    def get_policy(self, _tenant_id, _project_id):
        return SimpleNamespace(
            allowed_origins=["https://example.test"], vision_max_hops=0, vision_max_states=1
        )


class Events:
    def __init__(self):
        self.items = []

    def append(self, event):
        self.items.append(event)


class ReplayStore:
    def __init__(self) -> None:
        self.frames = []

    def write_replay_frame(self, frame, content: bytes) -> None:
        assert frame.checksum == hashlib.sha256(content).hexdigest()
        self.frames.append((frame, content))


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


def test_capture_is_durably_stored_before_temporary_provider_delivery(
    monkeypatch, tmp_path
) -> None:
    class CaptureSessions(Sessions):
        def __init__(self, session):
            super().__init__(session)
            self.states, self.frames, self.actions = [], [], []

        def add_state(self, state):
            self.states.append(state)

        def add_replay_frame(self, frame):
            self.frames.append(frame)
            return frame

        def add_action(self, action):
            self.actions.append(action)

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kwargs):
            state_id = kwargs["json"]["node_id"]
            path = tmp_path / "vision" / str(session.id) / f"tree-{state_id}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x89PNG\r\n\x1a\ncaptured")
            return SimpleNamespace(raise_for_status=lambda: None)

        async def delete(self, *_args, **_kwargs):
            return SimpleNamespace(raise_for_status=lambda: None)

    class TemporaryImageStore:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return "https://temporary.example/image"

        async def __aexit__(self, *_args):
            return None

        def deliver(self, **_kwargs):
            return self

    session = SimpleNamespace(
        id=uuid4(), tenant_id="tenant-a", correlation_id=uuid4(), state="queued",
        project_id=uuid4(),
        encrypted_task_intent="",
        intent_retention_until=datetime.now(UTC) + timedelta(days=1),
        max_hops=0, max_states=1, target_url="https://example.test", policy_version="policy-v1",
        provider="provider", model="model", prompt_version="prompt-v1",
    )
    sessions, events, replay_store = CaptureSessions(session), Events(), ReplayStore()
    runtime = SimpleNamespace(
        vision=SimpleNamespace(
            enabled=True, raw_screenshot_transfer_accepted=True, max_session_seconds=10,
            max_screenshot_bytes=1_000, max_requests_per_minute=60,
        )
    )
    monkeypatch.setattr("application.vision_events.resolve_agent_runtime", lambda *_args: runtime)
    monkeypatch.setattr("application.vision_events.decrypt_visual_intent", lambda *_args: "safe")
    monkeypatch.setattr("application.vision_events.httpx.AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(
        "application.vision_events.GoogleDriveTemporaryVisionImageStore", TemporaryImageStore
    )
    monkeypatch.setattr(
        "application.vision_events.execute_visual_candidate_batch",
        lambda **_kwargs: asyncio.sleep(0, result=VisualCandidateBatchOutcome(
            status="completed", actions=[VisualAction(kind="stop", confidence=0.9)]
        )),
    )
    monkeypatch.setattr(
        "application.vision_events.create_vision_language_model", lambda *_args: object()
    )

    processor = VisionEventProcessor(
        sessions, Configs(), Generation(), events, events, events,
        Settings(artifact_root=str(tmp_path), vision_worker_secret="worker-secret"), replay_store,
    )

    assert asyncio.run(processor.execute(event(session))) == "completed"
    assert len(replay_store.frames) == len(sessions.frames) == 1
    frame, content = replay_store.frames[0]
    assert frame.state_id == sessions.states[0].id
    assert frame.content_type == "image/png"
    assert content.startswith(b"\x89PNG")
    assert sessions.actions == []
