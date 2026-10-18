"""Origin-only audit metadata never gates live exploration."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from application.vision_origins import RecordVisualOrigins
from auto_at.contracts.vision_worker import VisualExternalOrigin, VisualWorkerOriginObservations
from domain.activity import ActivityEvent
from pydantic import ValidationError


def test_origin_audit_deduplicates_and_records_truncation_and_transport_failure():
    identity = dict(tenant_id="fixture", project_id=uuid4(), session_id=uuid4(), fencing_token=1)
    observations = VisualWorkerOriginObservations(**identity, truncated=True, items=[
        VisualExternalOrigin(origin="https://cdn.fixture.test", request_kind="resource",
                             observed_at=datetime.now(UTC)),
    ])
    operations = SimpleNamespace(worker=Mock(origins=AsyncMock(return_value=observations)),
                                 uow=Mock(), lease=object(), identity=identity)
    recorder = RecordVisualOrigins(operations)
    asyncio.run(recorder.capture())
    asyncio.run(recorder.capture())
    assert operations.uow.progress.call_count == 2
    event = operations.uow.progress.call_args_list[0]
    assert event.args[1] == "origin.observed"
    assert event.args[3] == {"origin": "https://cdn.fixture.test", "request_kind": "resource"}
    operations.worker.origins.side_effect = ConnectionError("private diagnostic")
    asyncio.run(recorder.capture())
    asyncio.run(recorder.capture())
    assert operations.uow.progress.call_count == 3
    assert operations.uow.progress.call_args.args[1] == "origin.observation_unavailable"


@pytest.mark.parametrize("origin", [
    "https://user:secret@example.test", "https://example.test/path",
    "https://example.test?token=secret", "https://example.test#fragment",
    "file:///tmp/private", "https://example.test\n", "*",
])
def test_origin_metadata_rejects_credentials_paths_and_non_http_urls(origin):
    with pytest.raises(ValidationError):
        VisualExternalOrigin(origin=origin, request_kind="resource", observed_at=datetime.now(UTC))
    with pytest.raises(ValueError):
        ActivityEvent.create_vision_progress(
            tenant_id="fixture", correlation_id=uuid4(), visual_exploration_session_id=uuid4(),
            stage="origin.observed", progress_key="origin", occurred_at=datetime.now(UTC),
            metadata={"origin": origin, "request_kind": "resource"},
        )
