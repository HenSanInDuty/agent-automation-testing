"""Temporal implementation of the local durable run-dispatch workflow."""

import logging
from datetime import UTC, datetime

from application.runs import (
    DispatchRun,
    RecordDeterministicResult,
    RequestFailureTriage,
    RequestRunReport,
)
from auto_at.contracts.execution import TestExecutionRequest
from config import Settings
from domain.activity import ActivityEvent
from domain.runs import OutboxEvent
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from infrastructure.runners import HttpPlaywrightTransport, VerifiedLocalArtifactPort
from infrastructure.workflows.definitions import RunWorkflowInput, TestRunWorkflow


def _requested_at(value: object) -> str | None:
    return value if isinstance(value, str) else None


logger = logging.getLogger(__name__)


@activity.defn(name="auto-at.dispatch-test-run.v1")
def dispatch_test_run(payload: RunWorkflowInput) -> dict[str, str]:
    """Activity that persists only the observed runner result as terminal state."""
    settings = Settings()
    request = TestExecutionRequest.model_validate(payload.request)
    attempt = activity.info().attempt
    if attempt > 1:
        logger.warning(
            "run.retry run_id=%s correlation_id=%s attempt=%s",
            request.run_id,
            request.correlation_id,
            attempt,
        )
    with transactional_session(create_session_factory(settings)) as session:
        runs = SqlAlchemyRunRepository(session)
        activities = SqlAlchemyActivityEventRepository(session)
        activities.append(
            ActivityEvent.create(
                tenant_id=payload.tenant_id,
                run_id=request.run_id,
                correlation_id=request.correlation_id,
                source="workflow",
                stage="dispatch",
                status="running",
                safe_summary="Durable workflow dispatched the browser run.",
                occurred_at=datetime.now(UTC),
                metadata={"attempt": attempt},
            )
        )
        run, result = DispatchRun(
            runs,
            HttpPlaywrightTransport(
                settings.playwright_worker_url, progress_tenant_id=payload.tenant_id
            ),
        ).execute(payload.tenant_id, request)
        VerifiedLocalArtifactPort(
            settings.artifact_root, SqlAlchemyArtifactRepository(session)
        ).persist_result_artifacts(payload.tenant_id, result, request.artifact_policy.retain_days)
        run = RecordDeterministicResult(runs).execute(payload.tenant_id, result)
        activities.append(
            ActivityEvent.create(
                tenant_id=payload.tenant_id,
                run_id=request.run_id,
                correlation_id=request.correlation_id,
                source="workflow",
                stage="completed",
                status=result.status.value,
                safe_summary="Runner returned its deterministic result.",
                occurred_at=datetime.now(UTC),
            )
        )
        RequestFailureTriage(
            SqlAlchemyOutboxEventRepository(session),
            SqlAlchemyAuditEventRepository(session),
            activities,
        ).execute(run)
        RequestRunReport(
            SqlAlchemyOutboxEventRepository(session),
            SqlAlchemyAuditEventRepository(session),
            activities,
        ).execute(run)
    return {"run_id": str(run.id), "status": result.status.value}


class TemporalWorkflowStarter:
    """Starts one workflow per run; an existing workflow is a successful duplicate delivery."""

    def __init__(self, client: Client, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def start_run(self, event: OutboxEvent) -> None:
        run_id = str(event.payload["run_id"])
        request = event.payload.get("request")
        if not isinstance(request, dict):
            raise ValueError("run request event is missing its execution request")
        try:
            await self._client.start_workflow(
                TestRunWorkflow.run,
                RunWorkflowInput(
                    tenant_id=event.tenant_id,
                    request=request,
                    requested_at=_requested_at(event.payload.get("requested_at")),
                    activity_timeout_seconds=self._settings.temporal_activity_timeout_seconds,
                    run_deadline_seconds=self._settings.temporal_run_deadline_seconds,
                    retry_initial_interval_seconds=(
                        self._settings.temporal_retry_initial_interval_seconds
                    ),
                    retry_maximum_interval_seconds=(
                        self._settings.temporal_retry_maximum_interval_seconds
                    ),
                    retry_maximum_attempts=self._settings.temporal_retry_maximum_attempts,
                ),
                id=f"auto-at-run-{run_id}",
                task_queue=self._settings.temporal_task_queue,
            )
        except WorkflowAlreadyStartedError:
            return

    async def cancel_run(self, event: OutboxEvent) -> None:
        """Propagate durable cancellation to both the workflow and worker."""
        run_id = str(event.payload["run_id"])
        logger.info(
            "run.cancellation.requested run_id=%s correlation_id=%s",
            run_id,
            event.correlation_id,
        )
        await self._client.get_workflow_handle(f"auto-at-run-{run_id}").cancel()
        HttpPlaywrightTransport(self._settings.playwright_worker_url).cancel(run_id)
