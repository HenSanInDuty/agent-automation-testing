from uuid import uuid4

from infrastructure.observability import Metrics, trace_context


def test_trace_context_preserves_correlation_id_and_w3c_shape() -> None:
    correlation_id = uuid4()
    context = trace_context(correlation_id)

    assert context.correlation_id == correlation_id
    assert len(context.traceparent().split("-")) == 4


def test_trace_context_keeps_valid_upstream_trace_id() -> None:
    upstream_trace_id = "a" * 32
    context = trace_context(uuid4(), f"00-{upstream_trace_id}-{'b' * 16}-01")

    assert context.traceparent().split("-")[1] == upstream_trace_id


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
