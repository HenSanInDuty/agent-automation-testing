from uuid import uuid4

from auto_at.contracts.execution import TargetType
from domain.runs import TestRun as DomainTestRun
from infrastructure.persistence.models import ProjectModel
from infrastructure.persistence.models import TestCaseModel as DbTestCaseModel
from infrastructure.persistence.repositories import SqlAlchemyRunRepository
from infrastructure.persistence.session import create_engine
from sqlalchemy.orm import Session


def test_run_repository_scopes_reads_to_the_tenant() -> None:
    from config import Settings

    engine = create_engine(Settings())
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        project_id = uuid4()
        session.add(
            ProjectModel(
                id=project_id,
                tenant_id="tenant-a",
                name="Shop",
                default_target="web_ui",
            )
        )
        session.add(
            DbTestCaseModel(
                id="checkout-repository-test",
                tenant_id="tenant-a",
                project_id=project_id,
                target_type=TargetType.WEB_UI,
                revision="a" * 40,
            )
        )
        run = DomainTestRun.create(
            tenant_id="tenant-a",
            project_id=project_id,
            test_case_id="checkout-repository-test",
            revision="a" * 40,
            correlation_id=uuid4(),
        )
        repository = SqlAlchemyRunRepository(session)
        repository.add(run)

        assert repository.get("tenant-a", run.id) == run
        assert repository.get("tenant-b", run.id) is None
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
