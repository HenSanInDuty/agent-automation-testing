import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agents.shared.runtime import VisionPolicy
from agents.vision.diagnostics import (
    VisionProviderFailure,
    VisualDiagnosticCapture,
    VisualDiagnosticCode,
)
from agents.vision.executor import VisualCandidateBatchOutcome
from application.vision_events import VisionEventProcessor
from config import Settings
from domain.runs import OutboxEvent
from infrastructure.vision.model_batch import VisionModelBatch


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


def test_interrupted_legacy_session_does_not_replay_uncertain_browser_actions():
    session = SimpleNamespace(
        id=uuid4(), tenant_id="tenant-a", correlation_id=uuid4(), state="running",
    )
    events = Events()
    processor = VisionEventProcessor(
        Sessions(session), object(), object(), events, events, events, Settings(_env_file=None),
    )
    assert asyncio.run(processor.execute(event(session))) == "unavailable"
    assert session.safe_failure_reason == "visual_exploration_unavailable"
    assert asyncio.run(processor.execute(event(session))) == "already_processed"


@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
@pytest.mark.parametrize("variant", [
    "success", "switch_before", "switch_after", "revoke", "origin", "model", "disabled",
    "provider_auth_failed", "provider_billing_required", "provider_rate_limited",
    "provider_timeout", "model_output_invalid", "missing_key", "image_auth", "step_limit",
])
def test_capture_is_durably_stored_before_temporary_provider_delivery(
    monkeypatch, tmp_path, provider, variant
) -> None:
    class CaptureSessions(Sessions):
        def __init__(self, session):
            super().__init__(session)
            self.states, self.frames, self.actions, self.edges = [], [], [], []

        def add_state(self, state):
            self.states.append(state)

        def add_replay_frame(self, frame):
            self.frames.append(frame)
            return frame

        def add_action(self, action):
            self.actions.append(action)

        def add_trajectory_edge(self, edge):
            self.edges.append(edge)
            return edge

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
            if variant == "switch_before":
                change_policy()
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "url_fingerprint": "a" * 64,
                    "url_change": "unavailable",
                    "duration_ms": 3,
                },
            )

        async def delete(self, *_args, **_kwargs):
            return SimpleNamespace(raise_for_status=lambda: None)

    class TemporaryImageStore:
        def __init__(self, *_args, **_kwargs):
            assert provider == "huggingface", "Gemini must not construct Drive"

        async def __aenter__(self):
            if variant == "image_auth":
                from domain.vision import VisionImageAuthorizationRequired
                raise VisionImageAuthorizationRequired("image_delivery_auth_required")
            return "https://temporary.example/image"

        async def __aexit__(self, *_args):
            return None

        def deliver(self, **_kwargs):
            return self

    class ExplorationGeneration:
        def get_policy(self, _tenant_id, _project_id):
            return SimpleNamespace(
                allowed_origins=["https://example.test"],
                vision_max_hops=2 if variant == "step_limit" else 1, vision_max_states=3
            )

    session = SimpleNamespace(
        id=uuid4(), tenant_id="tenant-a", correlation_id=uuid4(), state="queued",
        project_id=uuid4(),
        encrypted_task_intent="",
        intent_retention_until=datetime.now(UTC) + timedelta(days=1),
        max_hops=2 if variant == "step_limit" else 1, max_states=3,
        max_steps=1 if variant == "step_limit" else 3, max_screenshot_bytes=1_000_000,
        max_session_seconds=10, max_requests_per_minute=10_000,
        target_url="https://example.test", policy_version="policy-v1",
        provider=provider, model="gemini-3.8-flash" if provider == "gemini" else "fixture-model",
        prompt_version="prompt-v1",
    )
    sessions, events, replay_store = CaptureSessions(session), Events(), ReplayStore()
    policy = VisionPolicy(
        enabled=True, provider=provider, model=session.model,
        raw_screenshot_transfer_accepted=True, raw_screenshot_transfer_provider=provider,
        max_session_seconds=10, max_requests_per_minute=10_000,
    )
    project_policy = ExplorationGeneration().get_policy(None, None)
    config = {"vision": policy.model_dump()}
    calls = []

    def change_policy():
        if variant in {"switch_before", "switch_after"}:
            other = "huggingface" if provider == "gemini" else "gemini"
            config["vision"].update(
                provider=other, model="gemini-3.8-flash" if other == "gemini" else "other-hf",
                raw_screenshot_transfer_provider=other,
            )
        elif variant == "origin":
            project_policy.allowed_origins = ["https://different.test"]
        elif variant == "model":
            config["vision"]["model"] = "other-model"
        elif variant == "revoke":
            config["vision"]["raw_screenshot_transfer_provider"] = (
                "gemini" if provider == "huggingface" else "huggingface"
            )
        elif variant == "disabled":
            config["vision"]["enabled"] = False

    def read_policy(*_):
        # Return detached snapshots like the real reader.
        return config, SimpleNamespace(**vars(project_policy))

    class Model:
        async def ainvoke(self, payload, **kwargs):
            assert sessions.frames and replay_store.frames
            image_url = payload["messages"][1]["content"][1]["image_url"]["url"]
            assert image_url.startswith("data:image/png") == (provider == "gemini")
            calls.append(payload)
            change_policy()
            if variant.startswith("provider_"):
                raise VisionProviderFailure(variant)
            content = "invalid" if variant == "model_output_invalid" else json.dumps({
                "candidates": [{"kind": "click", "x": 0.5, "y": 0.5,
                             "confidence": 0.9, "expected_outcome": "fixture"}]
            })
            return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr("application.vision_events.decrypt_visual_intent", lambda *_args: "safe")
    monkeypatch.setattr("application.vision_events.httpx.AsyncClient", lambda **_kwargs: Client())
    settings = Settings(
        _env_file=None, artifact_root=str(tmp_path), vision_worker_secret="worker-secret",
        gemini_api_key=None if variant == "missing_key" else "synthetic-gemini",
        huggingface_api_key=None if variant == "missing_key" else "synthetic-hf",
    )
    processor = VisionEventProcessor(
        sessions, Configs(), ExplorationGeneration(), events, events, events,
        settings, replay_store, read_policy=read_policy,
        model_batch=VisionModelBatch(
            settings, model_factory=lambda *_args, **_kwargs: Model(),
            image_store_factory=TemporaryImageStore,
        ),
    )
    expected_reason = (
        "policy_disabled" if variant in {
            "switch_before", "switch_after", "revoke", "origin", "model", "disabled"
        } else "provider_not_configured" if variant == "missing_key"
        else "image_delivery_auth_required" if variant == "image_auth" and provider == "huggingface"
        else variant if variant.startswith("provider_") or variant in {
            "model_output_invalid", "step_limit"
        } else None
    )
    if expected_reason:
        assert asyncio.run(processor.execute(event(session))) == "unavailable"
        assert session.safe_failure_reason == expected_reason
        assert len(sessions.frames) == (2 if variant == "step_limit" else 1)
        assert len(sessions.actions) == (1 if variant == "step_limit" else 0)
        assert any(getattr(e, "metadata", {}).get("reason_code") == expected_reason
                   for e in events.items)
        assert not any(getattr(e, "stage", "") == "draft.handoff" for e in events.items)
        call_count = len(calls)
        assert asyncio.run(processor.execute(event(session))) == "already_processed"
        assert len(calls) == call_count
        return

    assert asyncio.run(processor.execute(event(session))) == "completed"
    assert len(replay_store.frames) == len(sessions.frames) == 2
    frame, content = replay_store.frames[0]
    assert frame.state_id == sessions.states[0].id
    assert frame.content_type == "image/png"
    assert content.startswith(b"\x89PNG")
    assert len(sessions.actions) == 1
    assert [edge.status for edge in sessions.edges] == ["proposed", "terminal"]
    assert sessions.edges[-1].outcome_code == "hop_limit"
    assert any(item.stage == "edge.proposed" for item in events.items)
    assert any(item.stage == "edge.terminal" for item in events.items)
