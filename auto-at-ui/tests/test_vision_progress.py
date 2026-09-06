"""Safe, session-scoped progress records for advisory visual exploration."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from application.vision_events import VisionEventProcessor
from config import Settings
from domain.activity import ActivityEvent


class Events:
    def __init__(self) -> None:
        self.items = []

    def append(self, event) -> None:
        self.items.append(event)


@pytest.mark.parametrize(
    ("stage", "metadata"),
    [
        ("queued", {}),
        ("started", {}),
        ("state.captured", {"state_sequence": 1, "hop": 0}),
        ("candidate.requested", {"state_sequence": 1, "hop": 0}),
        ("candidate.received", {"state_sequence": 1, "candidate_count": 2}),
        ("action.recorded", {"action_sequence": 1, "action_kind": "click"}),
        ("limit.reached", {"state_count": 5}),
        ("draft.handoff", {"outcome": "accepted"}),
        ("completed", {"state_count": 1, "action_count": 1}),
        ("unavailable", {}),
    ],
)
def test_vision_progress_stages_are_session_scoped(stage: str, metadata: dict[str, object]) -> None:
    session_id = uuid4()
    event = ActivityEvent.create_vision_progress(
        tenant_id="tenant-a",
        correlation_id=uuid4(),
        visual_exploration_session_id=session_id,
        stage=stage,
        progress_key=f"{stage}:1",
        occurred_at=datetime.now(UTC),
        metadata=metadata,
    )

    assert event.source == "vision"
    assert event.visual_exploration_session_id == session_id


def test_vision_progress_allows_only_closed_safe_metadata() -> None:
    session_id, correlation_id = uuid4(), uuid4()
    event = ActivityEvent.create_vision_progress(
        tenant_id="tenant-a",
        correlation_id=correlation_id,
        visual_exploration_session_id=session_id,
        stage="action.recorded",
        progress_key="action.recorded:1",
        occurred_at=datetime.now(UTC),
        metadata={"action_sequence": 1, "action_kind": "click", "confidence": 0.9},
    )

    assert event.visual_exploration_session_id == session_id
    assert event.metadata == {"action_sequence": 1, "action_kind": "click", "confidence": 0.9}
    serialized = str(event)
    for forbidden in ("typed-text", "task-intent", "https://image.test", "provider-response"):
        assert forbidden not in serialized

    with pytest.raises(ValueError, match="allow-listed"):
        ActivityEvent.create_vision_progress(
            tenant_id="tenant-a",
            correlation_id=correlation_id,
            visual_exploration_session_id=session_id,
            stage="action.recorded",
            progress_key="action.recorded:2",
            occurred_at=datetime.now(UTC),
            metadata={"text": "typed-text"},
        )


def test_unavailable_progress_is_session_scoped_and_redacted() -> None:
    session = SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        correlation_id=uuid4(),
        state="running",
        safe_failure_reason=None,
    )
    events = Events()
    processor = VisionEventProcessor(
        object(), object(), object(), events, events, events, Settings()
    )

    result = processor._unavailable(session, "provider response: token=sentinel-secret")
    assert result == "unavailable"
    progress = events.items[0]
    assert progress.stage == "unavailable"
    assert progress.visual_exploration_session_id == session.id
    assert "sentinel-secret" not in str(progress)
    assert "provider response" not in str(progress)
