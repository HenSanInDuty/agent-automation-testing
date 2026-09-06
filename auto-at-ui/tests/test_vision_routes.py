"""Session-scoped Vision activity route behavior."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from api.v1.routes import vision as vision_routes
from api.v1.routes.activities import ActivityResponse


def _activity(session_id, *, stage: str = "state.captured") -> ActivityResponse:
    return ActivityResponse(
        id=uuid4(),
        run_id=None,
        correlation_id=uuid4(),
        source="vision",
        stage=stage,
        status="running",
        safe_summary="Safe browser state was captured.",
        metadata={"state_sequence": 1},
        occurred_at=datetime.now(UTC),
    )


def test_session_stream_resumes_and_uses_named_safe_activity_events(monkeypatch) -> None:
    session_id = uuid4()
    first, second = _activity(session_id), _activity(session_id, stage="candidate.received")
    calls = []

    def activities(*args):
        calls.append(args)
        return [first, second]

    monkeypatch.setattr(vision_routes, "_session_activities", activities)

    async def collect() -> list[str]:
        response = await vision_routes.stream_exploration_activities(
            session_id=session_id,
            last_event_id=str(first.id),
            tenant_id="tenant-a",
            principal=None,
            settings=None,
        )
        iterator = response.body_iterator
        messages = [await anext(iterator), await anext(iterator)]
        await iterator.aclose()
        return messages

    event, keepalive = asyncio.run(collect())
    assert f"id: {second.id}" in event
    assert "event: activity" in event
    assert str(first.id) not in event
    assert "typed-text" not in event
    assert keepalive == ": keepalive\n\n"
    assert calls[0][0] == session_id


def test_session_stream_ends_when_a_later_authorized_refresh_fails(monkeypatch) -> None:
    session_id = uuid4()
    calls = 0

    def activities(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(vision_routes, "_session_activities", activities)

    async def collect() -> list[str]:
        response = await vision_routes.stream_exploration_activities(
            session_id=session_id, tenant_id="tenant-a", principal=None, settings=None
        )
        iterator = response.body_iterator
        result = [item async for item in iterator]
        await iterator.aclose()
        return result

    assert asyncio.run(collect()) == []
