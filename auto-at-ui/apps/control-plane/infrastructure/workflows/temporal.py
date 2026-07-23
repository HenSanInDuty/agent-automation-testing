"""Temporal implementation of the local durable run-dispatch workflow."""

from application.runs import DispatchRun, RecordDeterministicResult
from auto_at.contracts.execution import TestExecutionRequest
from config import Settings
from domain.runs import OutboxEvent
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from infrastructure.persistence.repositories import (
    SqlAlchemyArtifactRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from infrastructure.runners import HttpPlaywrightTransport, VerifiedLocalArtifactPort
from infrastructure.workflows.definitions import RunWorkflowInput, TestRunWorkflow


@activity.defn(name="auto-at.dispatch-test-run.v1")
def dispatch_test_run(payload: RunWorkflowInput) -> dict[str, str]:
    """Activity that persists only the observed runner result as terminal state."""
    settings = Settings()
    request = TestExecutionRequest.model_validate(payload.request)
    with transactional_session(create_session_factory(settings)) as session:
        runs = SqlAlchemyRunRepository(session)
        run, result = DispatchRun(
            runs, HttpPlaywrightTransport(settings.playwright_worker_url)
        ).execute(payload.tenant_id, request)
        VerifiedLocalArtifactPort(
            settings.artifact_root, SqlAlchemyArtifactRepository(session)
        ).persist_result_artifacts(payload.tenant_id, result, request.artifact_policy.retain_days)
        RecordDeterministicResult(runs).execute(payload.tenant_id, result)
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
                RunWorkflowInput(tenant_id=event.tenant_id, request=request),
                id=f"auto-at-run-{run_id}",
                task_queue=self._settings.temporal_task_queue,
            )
        except WorkflowAlreadyStartedError:
            return
