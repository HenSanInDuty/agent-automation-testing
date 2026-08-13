from uuid import uuid4

from config import Settings
from fastapi.testclient import TestClient
from infrastructure.persistence.models import ProjectModel, TestCaseModel
from infrastructure.persistence.session import create_engine
from main import app
from sqlalchemy import delete
from sqlalchemy.orm import Session


def test_project_admin_can_rename_a_test_case_but_contributor_cannot() -> None:
    tenant_id = f"catalog-name-{uuid4()}"
    project_id = uuid4()
    test_case_id = f"checkout-{uuid4()}"
    engine = create_engine(Settings())
    try:
        with Session(engine) as session:
            session.add(
                ProjectModel(
                    id=project_id,
                    tenant_id=tenant_id,
                    name="Catalog test project",
                    default_target="web_ui",
                )
            )
            session.add(
                TestCaseModel(
                    id=test_case_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    name="Original test name",
                    target_type="web_ui",
                    revision="a" * 40,
                    specification={},
                )
            )
            session.commit()

        client = TestClient(app)
        contributor = client.put(
            f"/api/v1/projects/{project_id}/tests/{test_case_id}/name",
            headers={"X-Tenant-Id": tenant_id, "X-Actor-Roles": "contributor"},
            json={"name": "Renamed checkout test"},
        )
        assert contributor.status_code == 404

        renamed = client.put(
            f"/api/v1/projects/{project_id}/tests/{test_case_id}/name",
            headers={"X-Tenant-Id": tenant_id, "X-Actor-Roles": "project_admin"},
            json={"name": "Renamed checkout test"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Renamed checkout test"

        listed = client.get(
            f"/api/v1/projects/{project_id}/tests",
            headers={"X-Tenant-Id": tenant_id},
        )
        assert listed.status_code == 200
        assert listed.json()[0]["name"] == "Renamed checkout test"
    finally:
        with Session(engine) as session:
            session.execute(delete(TestCaseModel).where(TestCaseModel.id == test_case_id))
            session.execute(delete(ProjectModel).where(ProjectModel.id == project_id))
            session.commit()
