"""Deterministic Temporal workflow definitions with no infrastructure imports."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass(frozen=True)
class RunWorkflowInput:
    tenant_id: str
    request: dict[str, Any]
    requested_at: str | None = None
    activity_timeout_seconds: int = 600
    run_deadline_seconds: int = 1_200
    retry_initial_interval_seconds: int = 1
    retry_maximum_interval_seconds: int = 30
    retry_maximum_attempts: int = 3


@workflow.defn(name="auto-at.test-run.v1")
class TestRunWorkflow:
    """Retry unavailable infrastructure, never a runner-reported functional failure."""

    @workflow.run
    async def run(self, payload: RunWorkflowInput) -> dict[str, str]:
        queue_delay_ms = None
        if payload.requested_at is not None:
            queued_at = datetime.fromisoformat(payload.requested_at)
            queue_delay_ms = max(0, int((workflow.now() - queued_at).total_seconds() * 1_000))
        workflow.logger.info(
            "run.dispatch.started run_id=%s correlation_id=%s queue_delay_ms=%s",
            payload.request.get("run_id"),
            payload.request.get("correlation_id"),
            queue_delay_ms,
        )
        return await workflow.execute_activity(
            "auto-at.dispatch-test-run.v1",
            payload,
            start_to_close_timeout=timedelta(seconds=payload.activity_timeout_seconds),
            schedule_to_close_timeout=timedelta(seconds=payload.run_deadline_seconds),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=payload.retry_initial_interval_seconds),
                maximum_interval=timedelta(seconds=payload.retry_maximum_interval_seconds),
                maximum_attempts=payload.retry_maximum_attempts,
                non_retryable_error_types=["ValueError"],
            ),
        )
