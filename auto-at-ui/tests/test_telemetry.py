import json
import logging
from uuid import uuid4

from infrastructure.observability import (
    JsonFormatter,
    Metrics,
    current_trace_context,
    redact,
    reset_trace_context,
    trace_context,
)


def test_trace_context_preserves_correlation_id_and_w3c_shape() -> None:
    correlation_id = uuid4()
    context = trace_context(correlation_id)

    assert context.correlation_id == correlation_id
    assert len(context.traceparent().split("-")) == 4


def test_trace_context_keeps_valid_upstream_trace_id() -> None:
    upstream_trace_id = "a" * 32
    context = trace_context(uuid4(), f"00-{upstream_trace_id}-{'b' * 16}-01")

    assert context.traceparent().split("-")[1] == upstream_trace_id


def test_trace_context_is_cleared_at_the_request_boundary() -> None:
    trace_context(uuid4())
    reset_trace_context()

    assert current_trace_context() is None


def test_json_formatter_has_context_and_redacts_secret_shaped_values() -> None:
    context = trace_context(uuid4())
    logger = logging.getLogger("test.telemetry")
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __file__,
        1,
        "Transport accepted bearer private-value?token=private-value",
        (),
        None,
        extra={"event": "runner.request.accepted", "run_id": "run-1", "authorization": "secret"},
    )

    payload = json.loads(JsonFormatter("test-service", "test").format(record))

    assert payload["correlation_id"] == str(context.correlation_id)
    assert payload["run_id"] == "run-1"
    assert "private-value" not in json.dumps(payload)
    assert payload["authorization"] == "[REDACTED]"
    assert redact({"token": "private"}) == {"token": "[REDACTED]"}
    reset_trace_context()


def test_metrics_exports_phase_six_metric_names() -> None:
    metrics = Metrics()
    for name in (
        "queue_delay",
        "run_duration",
        "retry_count",
        "failure_class",
        "artifact_failure",
        "agent_latency",
        "agent_cost",
        "proposal_acceptance",
        "false_healing",
    ):
        metrics.increment(name)

    assert metrics.snapshot()["false_healing"] == 1
    assert "auto_at_false_healing_total 1" in metrics.prometheus()
