from uuid import UUID, uuid4

import pytest
from application.runs import GetRun, ListArtifacts, RecordDeterministicResult, RunNotFoundError
from auto_at.contracts.execution import RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from domain.entities import ArtifactRecord
from domain.runs import TestRun as DomainTestRun


class InMemoryRuns:
    def __init__(self, run: DomainTestRun) -> None:
        self.run = run

    def get(self, tenant_id: str, run_id: UUID) -> DomainTestRun | None:
        if self.run.tenant_id == tenant_id and self.run.id == run_id:
            return self.run
        return None

    def save_result(self, run: DomainTestRun, result: ExecutionResult) -> None:
        run.record_runner_result(result)


def make_run() -> DomainTestRun:
    return DomainTestRun.create(
        tenant_id="tenant-a",
        project_id=uuid4(),
        test_case_id="checkout",
        revision="a" * 40,
        correlation_id=uuid4(),
    )


def test_get_run_rejects_another_tenant() -> None:
    run = make_run()

    with pytest.raises(RunNotFoundError):
        GetRun(InMemoryRuns(run)).execute("tenant-b", run.id)


def test_record_result_uses_the_runner_contract() -> None:
    run = make_run()
    result = ExecutionResult(
        run_id=run.id,
        correlation_id=run.correlation_id,
        status=RunStatus.PASSED,
        started_at="2026-07-21T09:00:00Z",
        completed_at="2026-07-21T09:01:00Z",
        summary="Passed.",
    )

    recorded = RecordDeterministicResult(InMemoryRuns(run)).execute("tenant-a", result)

    assert recorded.result == result
    assert recorded.status.value == "passed"


def test_list_artifacts_is_scoped_to_the_run_and_tenant() -> None:
    run = make_run()
    artifact = ArtifactRecord(
        id=uuid4(),
        tenant_id="tenant-a",
        run_id=run.id,
        kind="screenshot",
        uri="minio://artifacts/run.png",
        checksum="a" * 64,
        size=123,
    )

    class Artifacts:
        def list_for_run(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]:
            return [artifact] if (tenant_id, run_id) == ("tenant-a", run.id) else []

    assert ListArtifacts(Artifacts()).execute("tenant-a", run.id) == [artifact]
    assert ListArtifacts(Artifacts()).execute("tenant-b", run.id) == []
