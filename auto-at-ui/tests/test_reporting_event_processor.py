import asyncio
from uuid import UUID, uuid4

from application.reporting_events import ReportingEventProcessor
from auto_at.contracts.agent import RunReportStatus
from auto_at.contracts.events import EventType
from auto_at.contracts.execution import RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from config import Settings
from domain.entities import ArtifactRecord, RunReportRecord
from domain.runs import OutboxEvent, TestRun


class FakeModel:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls = 0

    async def ainvoke(self, payload: object, **kwargs: object) -> object:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class Reports:
    def __init__(self) -> None:
        self.items: dict[tuple[str, UUID, int], RunReportRecord] = {}

    def get_for_run(
        self, tenant_id: str, run_id: UUID, report_version: int = 1
    ) -> RunReportRecord | None:
        return self.items.get((tenant_id, run_id, report_version))

    def add(self, report: RunReportRecord) -> RunReportRecord:
        return self.items.setdefault(
            (report.tenant_id, report.run_id, report.report_version), report
        )


class NoArtifactReader:
    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes:
        raise AssertionError("unexpected artifact read")


def terminal_run() -> TestRun:
    run = TestRun.create(
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
            status=RunStatus.PASSED,
            started_at="2026-08-13T00:00:00Z",
            completed_at="2026-08-13T00:00:01Z",
            summary="Passed.",
        )
    )
    return run


def event(run: TestRun) -> OutboxEvent:
    return OutboxEvent(
        id=uuid4(),
        tenant_id=run.tenant_id,
        event_type=EventType.AGENT_RUN_REPORT_REQUESTED.value,
        schema_version="v1",
        correlation_id=run.correlation_id,
        causation_id=None,
        idempotency_key=f"run-report:{run.id}:v1",
        payload={"run_id": str(run.id)},
    )


def test_reporting_processor_persists_once_and_reuses_a_prior_report() -> None:
    run = terminal_run()
    reports = Reports()
    model = FakeModel(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"deterministic_status":"passed","headline":"Passed.",'
                            '"what_ran":"One test ran.","observations":[],"failure":null,'
                            '"unverified_or_skipped":[],"limitations":[]}'
                        )
                    }
                }
            ]
        }
    )

    class Runs:
        def get(self, tenant_id: str, run_id: UUID) -> TestRun | None:
            return run if tenant_id == run.tenant_id and run_id == run.id else None

    class Configs:
        def get(self, tenant_id: str, key: str) -> None:
            return None

    class Artifacts:
        def list_for_run(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]:
            return []

    processor = ReportingEventProcessor(
        Runs(),
        Configs(),
        Artifacts(),
        reports,
        NoArtifactReader(),
        Settings(),
        model_factory=lambda *_: model,
    )

    first = asyncio.run(processor.execute(event(run)))
    second = asyncio.run(processor.execute(event(run)))

    assert first.status == "completed"
    assert second.detail == "existing report reused"
    assert len(reports.items) == 1
    assert next(iter(reports.items.values())).status is RunReportStatus.COMPLETED
    assert model.calls == 1
    assert run.result is not None and run.result.status is RunStatus.PASSED


def test_reporting_processor_records_provider_failure_as_unavailable() -> None:
    run = terminal_run()
    reports = Reports()

    class Runs:
        def get(self, tenant_id: str, run_id: UUID) -> TestRun | None:
            return run

    class Configs:
        def get(self, tenant_id: str, key: str) -> None:
            return None

    class Artifacts:
        def list_for_run(self, tenant_id: str, run_id: UUID) -> list[ArtifactRecord]:
            return []

    processor = ReportingEventProcessor(
        Runs(),
        Configs(),
        Artifacts(),
        reports,
        NoArtifactReader(),
        Settings(),
        model_factory=lambda *_: FakeModel(RuntimeError("provider down")),
    )

    outcome = asyncio.run(processor.execute(event(run)))

    assert outcome.status == "unavailable"
    stored = next(iter(reports.items.values()))
    assert stored.status is RunReportStatus.UNAVAILABLE
    assert stored.deterministic_status is RunStatus.PASSED
