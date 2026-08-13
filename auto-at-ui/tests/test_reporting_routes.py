from uuid import uuid4

from auto_at.contracts.agent import RunReport, RunReportFailure, RunReportStatus
from auto_at.contracts.execution import RunStatus, TargetType
from domain.entities import RunReportRecord
from domain.runs import TestRun as DomainRun
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    ProjectModel,
    RunReportModel,
)
from infrastructure.persistence.models import (
    TestCaseModel as DbTestCaseModel,
)
from infrastructure.persistence.models import (
    TestRunModel as DbTestRunModel,
)
from infrastructure.persistence.repositories import (
    SqlAlchemyRunReportRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_engine
from main import app
from sqlalchemy import delete
from sqlalchemy.orm import Session


def test_run_report_route_is_tenant_scoped_and_returns_only_safe_report_fields() -> None:
    from config import Settings

    tenant_id = f"report-route-{uuid4()}"
    project_id = uuid4()
    test_case_id = f"report-route-{uuid4()}"
    engine = create_engine(Settings())
    run = DomainRun.create(
        tenant_id=tenant_id,
        project_id=project_id,
        test_case_id=test_case_id,
        revision="a" * 40,
        correlation_id=uuid4(),
    )
    try:
        with Session(engine) as session:
            session.add(
                ProjectModel(
                    id=project_id,
                    tenant_id=tenant_id,
                    name="Shop",
                    default_target="web_ui",
                )
            )
            session.add(
                DbTestCaseModel(
                    id=test_case_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    target_type=TargetType.WEB_UI,
                    revision="a" * 40,
                )
            )
            SqlAlchemyRunRepository(session).add(run)
            SqlAlchemyRunReportRepository(session).add(
                RunReportRecord.create(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    correlation_id=run.correlation_id,
                    deterministic_status=RunStatus.FAILED,
                    status=RunReportStatus.COMPLETED,
                    payload=RunReport(
                        deterministic_status="failed",
                        headline="Checkout assertion failed",
                        what_ran="The checkout test ran once.",
                        failure=RunReportFailure(
                            stage="assertion",
                            location="tests/checkout.spec.ts:12:4",
                            message="Expected confirmation heading.",
                            evidence_references=["artifacts/playwright-output.txt"],
                        ),
                        limitations=["No trace evidence was analyzed."],
                    ),
                    input_hash="a" * 64,
                    provenance={
                        "provider": "agent.runtime.v1",
                        "model": "configured-model",
                        "redaction_policy_version": "v1",
                        "raw_provider_response": "must not be exposed",
                    },
                )
            )
            session.commit()

        client = TestClient(app)
        response = client.get(f"/api/v1/runs/{run.id}/report", headers={"X-Tenant-Id": tenant_id})

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["payload"]["failure"]["location"] == "tests/checkout.spec.ts:12:4"
        assert payload["provenance"]["provider"] == "agent.runtime.v1"
        assert "raw_provider_response" not in str(payload)

        denied = client.get(
            f"/api/v1/runs/{run.id}/report", headers={"X-Tenant-Id": "other-tenant"}
        )
        assert denied.status_code == 404
    finally:
        with Session(engine) as session:
            session.execute(delete(RunReportModel).where(RunReportModel.run_id == run.id))
            session.execute(delete(DbTestRunModel).where(DbTestRunModel.id == run.id))
            session.execute(delete(DbTestCaseModel).where(DbTestCaseModel.id == test_case_id))
            session.execute(delete(ProjectModel).where(ProjectModel.id == project_id))
            session.commit()
        engine.dispose()
