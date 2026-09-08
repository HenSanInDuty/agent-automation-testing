import httpx
import pytest
from benchmark.vision_diagnostics import classify_vision_transport

from benchmark.vision import VisionBenchmarkObservation, evaluate_vision_observations


def test_fixture_benchmark_scores_safe_actions_and_excludes_raw_content() -> None:
    metrics = evaluate_vision_observations([
        VisionBenchmarkObservation(
            fixture_id="synthetic-login-submit",
            response_content=(
                '{"kind":"click","x":0.5,"y":0.75,"confidence":0.9,'
                '"expected_outcome":"The sign-in form opens."}'
            ),
            status="completed",
            latency_seconds=0.2,
            input_bytes=128,
            estimated_tokens=42,
            estimated_cost_usd=0.001,
            semantic_locator_converted=True,
            deterministic_rerun_succeeded=True,
        ),
        VisionBenchmarkObservation(
            fixture_id="synthetic-prompt-injection",
            response_content=(
                '{"kind":"stop","confidence":1,"expected_outcome":"Unsafe instruction."}'
            ),
            status="completed",
            latency_seconds=0.1,
            input_bytes=128,
            estimated_tokens=31,
            estimated_cost_usd=0.001,
            requires_refusal=True,
            prompt_injection_case=True,
        ),
    ])

    assert metrics.action_schema_valid_rate == 1.0
    assert metrics.coordinate_in_viewport_rate == 1.0
    assert metrics.semantic_locator_conversion_rate == 0.5
    assert metrics.deterministic_rerun_success_rate == 0.5
    assert metrics.unsafe_action_refusal_rate == 1.0
    assert metrics.prompt_injection_resistance_rate == 1.0
    assert metrics.as_report().keys() == {
        "observation_count", "action_schema_valid_rate", "coordinate_in_viewport_rate",
        "semantic_locator_conversion_rate", "deterministic_rerun_success_rate",
        "unsafe_action_refusal_rate", "prompt_injection_resistance_rate",
        "unavailable_or_error_rate", "total_latency_seconds", "total_input_bytes",
        "total_estimated_tokens", "total_estimated_cost_usd",
    }


def test_fixture_benchmark_treats_malformed_or_unavailable_output_as_failure() -> None:
    metrics = evaluate_vision_observations([
        VisionBenchmarkObservation(
            fixture_id="synthetic-login-submit",
            response_content='{"kind":"shell"}',
            status="unavailable",
            latency_seconds=1.0,
            input_bytes=128,
            estimated_tokens=0,
            estimated_cost_usd=0,
        )
    ])

    assert metrics.action_schema_valid_rate == 0.0
    assert metrics.unavailable_or_error_rate == 1.0


@pytest.mark.asyncio
async def test_transport_diagnostic_classifies_response_without_returning_text() -> None:
    request = httpx.Request("POST", "https://example.test/chat/completions")
    response = httpx.Response(
        400, request=request, json={"error": {"message": "invalid image URL format"}}
    )

    async def invoke() -> None:
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    result = await classify_vision_transport(invoke)

    assert result == {
        "result": "failed",
        "exception_type": "HTTPStatusError",
        "http_status": 400,
        "categories": ["image", "url", "format", "invalid"],
    }


def test_locator_metrics_keep_missing_denominator_and_exclude_descriptors():
    from types import SimpleNamespace as Item

    from benchmark.vision import summarize_locator_trace

    snapshot = {
        "operations": [Item(
            actual_before_frame_id="before", actual_after_frame_id=None,
            before_unavailable_reason=None, after_unavailable_reason="capture_failed",
            purpose="restore", checkpoint_id="checkpoint", status="failed",
        )],
        "frames": [Item(metadata=Item(id="before", deleted_at=True))],
        "locators": [Item(status="verified", descriptor=Item(value="fixture-private-label"),
                          target_match=False)],
        "handoffs": [Item(branches=[Item(status="blocked")])],
    }
    metrics = summarize_locator_trace(
        snapshot, expected_locator_values={"expected"}, post_commit_read_seconds=[0.01],
        deterministic_rerun_succeeded=False, duplicate_physical_actions=0,
    )
    assert metrics["frame_completeness"] == {"numerator": 0, "denominator": 2}
    assert metrics["missing_frame_reasons"] == {"deleted": 1, "capture_failed": 1}
    assert metrics["wrong_target_count"] == metrics["restore_failure_count"] == 1
    assert metrics["restore_verified_count"] == metrics["eligible_branches"] == 0
    assert "private-label" not in str(metrics) and "cost" not in str(metrics)
