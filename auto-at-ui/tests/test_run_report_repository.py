from uuid import uuid4

from auto_at.contracts.agent import RunReport, RunReportStatus
from auto_at.contracts.execution import RunStatus, TargetType
from domain.entities import RunReportRecord
from domain.runs import TestRun
from infrastructure.persistence.models import ProjectModel, TestCaseModel
from infrastructure.persistence.repositories import (
    SqlAlchemyRunReportRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_engine
from sqlalchemy.orm import Session


def test_run_report_repository_scopes_reads_and_makes_duplicate_add_idempotent() -> None:
    from config import Settings

    engine = create_engine(Settings())
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        project_id = uuid4()
        session.add(
            ProjectModel(id=project_id, tenant_id="tenant-a", name="Shop", default_target="web_ui")
        )
        session.add(
            TestCaseModel(
                id="run-report-test",
                tenant_id="tenant-a",
                project_id=project_id,
                target_type=TargetType.WEB_UI,
                revision="a" * 40,
            )
        )
        run = TestRun.create(
            tenant_id="tenant-a",
            project_id=project_id,
            test_case_id="run-report-test",
            revision="a" * 40,
            correlation_id=uuid4(),
        )
        SqlAlchemyRunRepository(session).add(run)
        report = RunReportRecord.create(
            tenant_id="tenant-a",
            run_id=run.id,
            correlation_id=run.correlation_id,
            deterministic_status=RunStatus.PASSED,
            status=RunReportStatus.COMPLETED,
            payload=RunReport(
                deterministic_status="passed", headline="Passed", what_ran="One test ran."
            ),
            input_hash="a" * 64,
        )
        repository = SqlAlchemyRunReportRepository(session)

        assert repository.add(report) == report
        assert repository.add(report) == report
        assert repository.get_for_run("tenant-a", run.id) == report
        assert repository.get_for_run("tenant-b", run.id) is None
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
