import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from infrastructure.workflows.definitions import RunWorkflowInput, TestRunWorkflow


def test_workflow_applies_bounded_retry_and_timeout_policy(monkeypatch) -> None:
    observed: dict[str, object] = {}
    log_messages: list[tuple[object, ...]] = []

    async def execute_activity(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return {"run_id": "run-1", "status": "passed"}

    monkeypatch.setattr(
        "infrastructure.workflows.definitions.workflow.execute_activity", execute_activity
    )
    monkeypatch.setattr(
        "infrastructure.workflows.definitions.workflow.logger.info",
        lambda *args, **kwargs: log_messages.append(args),
    )
    monkeypatch.setattr(
        "infrastructure.workflows.definitions.workflow.now",
        lambda: datetime(2026, 7, 25, 9, 0, 2, tzinfo=UTC),
    )
    run_id = uuid4()
    correlation_id = uuid4()
    payload = RunWorkflowInput(
        tenant_id="tenant-a",
        request={"run_id": str(run_id), "correlation_id": str(correlation_id)},
        requested_at="2026-07-25T09:00:00+00:00",
        activity_timeout_seconds=12,
        run_deadline_seconds=45,
        retry_initial_interval_seconds=2,
        retry_maximum_interval_seconds=8,
        retry_maximum_attempts=3,
    )

    assert asyncio.run(TestRunWorkflow().run(payload)) == {"run_id": "run-1", "status": "passed"}

    kwargs = observed["kwargs"]
    assert kwargs["start_to_close_timeout"].total_seconds() == 12
    assert kwargs["schedule_to_close_timeout"].total_seconds() == 45
    assert kwargs["retry_policy"].maximum_attempts == 3
    assert kwargs["retry_policy"].initial_interval.total_seconds() == 2
    assert kwargs["retry_policy"].maximum_interval.total_seconds() == 8
    assert kwargs["retry_policy"].non_retryable_error_types == ["ValueError"]
    assert log_messages == [
        (
            "run.dispatch.started run_id=%s correlation_id=%s queue_delay_ms=%s",
            str(run_id),
            str(correlation_id),
            2_000,
        )
    ]
