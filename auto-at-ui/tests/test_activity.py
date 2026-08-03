from datetime import UTC, datetime
from uuid import uuid4

import pytest
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
