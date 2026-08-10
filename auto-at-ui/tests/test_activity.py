import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from api.v1.routes import activities as activity_routes
from api.v1.routes.activities import ActivityResponse
from domain.activity import ActivityEvent


def test_activity_rejects_sensitive_metadata() -> None:
    with pytest.raises(ValueError, match="sensitive"):
        ActivityEvent.create(
            tenant_id="tenant-a", correlation_id=uuid4(), source="worker",
            stage="browser.launch", status="running", safe_summary="Launching browser.",
            occurred_at=datetime.now(UTC), metadata={"authorization": "Bearer secret"},
        )


def test_activity_is_append_only_safe_record() -> None:
    event = ActivityEvent.create(
        tenant_id="tenant-a", correlation_id=uuid4(), source="worker",
        stage="browser.launch", status="running", safe_summary="Launching browser.",
        occurred_at=datetime.now(UTC), metadata={"attempt": 1},
    )
    assert event.metadata == {"attempt": 1}


def test_activity_stream_resumes_after_last_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    first = ActivityResponse(
        id=uuid4(), run_id=uuid4(), correlation_id=uuid4(), source="workflow",
        stage="dispatch", status="running", safe_summary="Dispatching.",
        metadata={}, occurred_at=datetime.now(UTC),
    )
    second = ActivityResponse(
        id=uuid4(), run_id=first.run_id, correlation_id=first.correlation_id,
        source="worker", stage="browser.launch", status="running",
        safe_summary="Launching browser.", metadata={}, occurred_at=datetime.now(UTC),
    )

    monkeypatch.setattr(activity_routes, "list_activities", lambda *args: [first, second])

    async def collect() -> list[str]:
        response = await activity_routes.stream_activities(
            run_id=first.run_id, last_event_id=str(first.id), tenant_id="tenant-a",
            principal=None, settings=None,
        )
        iterator = response.body_iterator
        messages = [await anext(iterator), await anext(iterator)]
        await iterator.aclose()
        return messages

    events, keepalive = asyncio.run(collect())
    assert f"id: {second.id}" in events
    assert str(first.id) not in events
    assert keepalive == ": keepalive\n\n"
