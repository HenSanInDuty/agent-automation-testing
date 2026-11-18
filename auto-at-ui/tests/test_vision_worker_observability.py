"""Transport diagnostics retain correlation without exposing worker payloads."""

import asyncio
import json
import logging
from uuid import uuid4

import httpx
import pytest
from auto_at.contracts.vision_worker import VisualWorkerIdentity
from infrastructure.observability.logging import JsonFormatter
from infrastructure.observability.telemetry import reset_trace_context, trace_context
from infrastructure.vision_worker import HttpVisualWorker, VisualWorkerUnavailable


@pytest.mark.parametrize("detail,code", [
    ("session_unavailable", "session_unavailable"),
    ("capture_failed", "capture_failed"),
    ("private-page-content token=private", "worker_request_rejected"),
    ({"secret": "private"}, "worker_request_rejected"),
])
def test_rejected_screen_logs_scope_safe_code_and_propagates_trace(caplog, detail, code):
    identity = VisualWorkerIdentity(tenant_id="fixture", project_id=uuid4(),
                                    session_id=uuid4(), fencing_token=1)
    correlation = uuid4()

    async def read():
        context = trace_context(correlation)

        def reply(request):
            assert request.headers["x-correlation-id"] == str(correlation)
            assert request.headers["traceparent"] == context.traceparent()
            return httpx.Response(422, json={"detail": detail})

        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
                worker = HttpVisualWorker(client, "http://worker.test", "private-secret")
                await worker.screen(identity)
        finally:
            reset_trace_context()

    with caplog.at_level(logging.WARNING), pytest.raises(VisualWorkerUnavailable):
        asyncio.run(read())
    record = next(r for r in caplog.records if getattr(r, "event", "") == "vision.worker.rejected")
    payload = json.loads(JsonFormatter("auto-at-control-plane", "local").format(record))
    assert payload["session_id"] == str(identity.session_id)
    assert payload["code"] == code
    assert payload["status_code"] == 422
    assert payload["stage"] == "screen"
    assert payload["duration_ms"] >= 0
    assert "private" not in json.dumps(payload)


def test_transport_timeout_logs_category_without_exception_text(caplog):
    identity = VisualWorkerIdentity(tenant_id="fixture", project_id=uuid4(),
                                    session_id=uuid4(), fencing_token=1)

    def reply(request):
        assert "x-correlation-id" not in request.headers
        raise httpx.ReadTimeout("private-page-content", request=request)

    async def read():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            await HttpVisualWorker(client, "http://worker.test", "private-secret").screen(identity)

    with caplog.at_level(logging.WARNING), pytest.raises(VisualWorkerUnavailable):
        asyncio.run(read())
    record = next(r for r in caplog.records
                  if getattr(r, "event", "") == "vision.worker.transport_failed")
    assert record.error_type == "timeout"
    assert record.session_id == str(identity.session_id)
    assert "private" not in caplog.text
