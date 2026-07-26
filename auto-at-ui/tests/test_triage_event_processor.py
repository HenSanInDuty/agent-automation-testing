import asyncio
from uuid import uuid4

from application.triage_events import TriageEventProcessor
from auto_at.contracts.execution import RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from config import Settings
from domain.runs import OutboxEvent
from domain.runs import TestRun as DomainTestRun


def test_processor_returns_unavailable_without_openrouter_key() -> None:
    run = DomainTestRun.create(
        tenant_id="tenant-a",
        project_id=uuid4(),
        test_case_id="case",
        revision="a" * 40,
        correlation_id=uuid4(),
    )
    run.record_runner_result(
        ExecutionResult(
            run_id=run.id,
            correlation_id=run.correlation_id,
            status=RunStatus.FAILED,
            started_at="2026-07-26T00:00:00Z",
            completed_at="2026-07-26T00:00:01Z",
            summary="Failed.",
        )
    )

    class Runs:
        def get(self, tenant_id: str, run_id: object) -> DomainTestRun | None:
            return run

    class Configs:
        def get(self, tenant_id: str, key: str) -> None:
            return None

    class Proposals:
        def add(self, proposal: object) -> None:
            raise AssertionError("unavailable triage must not persist a proposal")

    event = OutboxEvent(
        id=uuid4(), tenant_id="tenant-a", event_type="agent.triage.requested.v1",
        schema_version="v1", correlation_id=run.correlation_id, causation_id=None,
        idempotency_key="triage:one", payload={"run_id": str(run.id)},
    )
    processor = TriageEventProcessor(
        Runs(), Configs(), Proposals(), Settings(openrouter_api_key=None)
    )
    outcome = asyncio.run(processor.execute(event))
    assert outcome.status == "unavailable"
