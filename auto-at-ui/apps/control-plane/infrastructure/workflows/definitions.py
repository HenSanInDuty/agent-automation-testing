"""Deterministic Temporal workflow definitions with no infrastructure imports."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass(frozen=True)
class RunWorkflowInput:
    tenant_id: str
    request: dict[str, Any]


@workflow.defn(name="auto-at.test-run.v1")
class TestRunWorkflow:
    """Retry unavailable infrastructure, never a runner-reported functional failure."""

    @workflow.run
    async def run(self, payload: RunWorkflowInput) -> dict[str, str]:
        return await workflow.execute_activity(
            "auto-at.dispatch-test-run.v1",
            payload,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=30),
                maximum_attempts=3,
                non_retryable_error_types=["ValueError"],
            ),
        )
