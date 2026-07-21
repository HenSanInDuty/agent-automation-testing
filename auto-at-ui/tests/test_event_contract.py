from uuid import uuid4

import pytest
from auto_at.contracts.events import EventEnvelope, EventType
from pydantic import ValidationError


def test_event_envelope_carries_delivery_and_trace_fields() -> None:
    correlation_id = uuid4()
    event = EventEnvelope(
        event_type=EventType.TEST_RUN_REQUESTED,
        correlation_id=correlation_id,
        causation_id=uuid4(),
        idempotency_key="run-request:checkout:1",
        payload={"run_id": str(uuid4())},
    )

    assert event.schema_version == "v1"
    assert event.correlation_id == correlation_id
    assert event.event_id
    assert event.occurred_at.tzinfo is not None


def test_event_envelope_requires_an_idempotency_key() -> None:
    with pytest.raises(ValidationError, match="idempotency_key"):
        EventEnvelope(
            event_type=EventType.TEST_RUN_REQUESTED,
            correlation_id=uuid4(),
            idempotency_key="",
        )
