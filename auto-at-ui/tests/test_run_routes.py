import hashlib
import io
from uuid import UUID, uuid4
from zipfile import ZipFile

from domain.runs import TestRun as DomainRun
from fastapi.testclient import TestClient
from infrastructure.persistence.models import (
    ArtifactModel,
    AuditEventModel,
    OutboxEventModel,
    ProjectModel,
)
from infrastructure.persistence.models import (
    TestCaseModel as DbTestCaseModel,
)
from infrastructure.persistence.models import (
    TestRunModel as DbTestRunModel,
)
from infrastructure.persistence.session import create_engine
from main import app
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


def test_create_run_requires_an_idempotency_key() -> None:
    response = TestClient(app).post(
        "/api/v1/runs",
        headers={"X-Tenant-Id": "tenant-a"},
        json={
            "project_id": str(uuid4()),
            "test_case_id": "checkout",
            "revision": "a" * 40,
        },
    )

    assert response.status_code == 422
    assert any(error["loc"][-1] == "Idempotency-Key" for error in response.json()["detail"])


def test_get_run_requires_authentication() -> None:
    response = TestClient(app).get(f"/api/v1/runs/{uuid4()}")

    assert response.status_code == 401


def test_create_run_commits_run_audit_and_outbox_atomically() -> None:
    from config import Settings

    tenant_id = "http-integration-tenant"
    project_id = uuid4()
    test_case_id = f"http-integration-{uuid4()}"
    correlation_id = uuid4()
    engine = create_engine(Settings())
    run_id: UUID | None = None
    try:
        with Session(engine) as session:
            session.add(
                ProjectModel(
                    id=project_id,
                    tenant_id=tenant_id,
                    name="HTTP integration project",
                    default_target="web_ui",
                )
            )
            session.add(
                DbTestCaseModel(
                    id=test_case_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    target_type="web_ui",
                    revision="a" * 40,
                )
            )
            session.commit()

        response = TestClient(app).post(
            "/api/v1/runs",
            headers={
                "Idempotency-Key": f"http-integration:{uuid4()}",
                "X-Tenant-Id": tenant_id,
            },
            json={
                "project_id": str(project_id),
                "test_case_id": test_case_id,
                "revision": "a" * 40,
                "correlation_id": str(correlation_id),
            },
        )

        assert response.status_code == 201
        run_id = UUID(response.json()["id"])
        with Session(engine) as session:
            run = session.scalar(select(DbTestRunModel).where(DbTestRunModel.id == run_id))
            audit = session.scalar(
                select(AuditEventModel).where(
                    AuditEventModel.entity_id == run_id,
                    AuditEventModel.action == "run.created",
                )
            )
            outbox = session.scalar(
                select(OutboxEventModel).where(
                    OutboxEventModel.correlation_id == correlation_id,
                    OutboxEventModel.event_type == "test.run.requested.v1",
                )
            )

        assert run is not None and run.status == "queued"
        assert audit is not None
        assert outbox is not None and outbox.payload["run_id"] == str(run_id)
        assert outbox.payload["request"]["run_id"] == str(run_id)
        traceparent = outbox.payload["request"]["runner_config"]["traceparent"]
        assert isinstance(traceparent, str) and len(traceparent.split("-")) == 4
    finally:
        with Session(engine) as session:
            if run_id is not None:
                session.execute(delete(AuditEventModel).where(AuditEventModel.entity_id == run_id))
                session.execute(delete(DbTestRunModel).where(DbTestRunModel.id == run_id))
            session.execute(
                delete(OutboxEventModel).where(OutboxEventModel.correlation_id == correlation_id)
            )
            session.execute(delete(DbTestCaseModel).where(DbTestCaseModel.id == test_case_id))
            session.execute(delete(ProjectModel).where(ProjectModel.id == project_id))
            session.commit()
        engine.dispose()


def test_artifact_archive_is_tenant_scoped_and_contains_verified_evidence(monkeypatch) -> None:
    from config import Settings

    settings = Settings()
    tenant_id = f"artifact-archive-{uuid4()}"
    project_id = uuid4()
    test_case_id = f"artifact-archive-{uuid4()}"
    run = DomainRun.create(
        tenant_id=tenant_id,
        project_id=project_id,
        test_case_id=test_case_id,
        revision="a" * 40,
        correlation_id=uuid4(),
    )
    zip_buffer = io.BytesIO()
    with ZipFile(zip_buffer, "w") as archive:
        archive.writestr("test-results/failure.txt", "Playwright assertion failed.")
        archive.writestr("resources/screenshot.png", b"png evidence")
    artifact_bytes = zip_buffer.getvalue()
    artifact_id = uuid4()
    artifact_uri = (
        f"s3://{settings.rustfs_bucket}/tenants/{tenant_id}/runs/{run.id}/artifacts/"
        "playwright-trace.zip"
    )

    class FakeStore:
        def __init__(self, _settings) -> None:
            pass

        def read_verified_bytes(self, artifact, _max_bytes):
            assert artifact.uri == artifact_uri
            assert artifact.checksum == hashlib.sha256(artifact_bytes).hexdigest()
            return artifact_bytes

    monkeypatch.setattr("api.v1.routes.runs.RustFSArtifactStore", FakeStore)
    engine = create_engine(settings)
    try:
        with Session(engine) as session:
            session.add(
                ProjectModel(
                    id=project_id,
                    tenant_id=tenant_id,
                    name="Artifact archive project",
                    default_target="web_ui",
                )
            )
            session.add(
                DbTestCaseModel(
                    id=test_case_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    target_type="web_ui",
                    revision="a" * 40,
                )
            )
            session.add(
                DbTestRunModel(
                    id=run.id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    test_case_id=test_case_id,
                    revision=run.revision,
                    status=run.status.value,
                    correlation_id=run.correlation_id,
                    version=run.version,
                )
            )
            session.flush()
            session.add(
                ArtifactModel(
                    id=artifact_id,
                    tenant_id=tenant_id,
                    run_id=run.id,
                    kind="playwright-trace",
                    uri=artifact_uri,
                    checksum=hashlib.sha256(artifact_bytes).hexdigest(),
                    size=len(artifact_bytes),
                    content_type="application/zip",
                )
            )
            session.commit()

        response = TestClient(app).get(
            f"/api/v1/runs/{run.id}/artifacts.zip", headers={"X-Tenant-Id": tenant_id}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert f'filename="run-{run.id}-artifacts.zip"' in response.headers["content-disposition"]
        with ZipFile(io.BytesIO(response.content)) as archive:
            filename = f"playwright-trace-{artifact_id}.zip"
            assert archive.namelist() == [filename]
            assert archive.read(filename) == artifact_bytes

        entries = TestClient(app).get(
            f"/api/v1/runs/{run.id}/artifacts/{artifact_id}/archive-entries",
            headers={"X-Tenant-Id": tenant_id},
        )
        assert entries.status_code == 200
        assert entries.json() == [
            {"path": "test-results/failure.txt", "size": 28, "is_directory": False},
            {"path": "resources/screenshot.png", "size": 12, "is_directory": False},
        ]

        denied = TestClient(app).get(
            f"/api/v1/runs/{run.id}/artifacts.zip", headers={"X-Tenant-Id": "other-tenant"}
        )
        assert denied.status_code == 404
    finally:
        with Session(engine) as session:
            session.execute(delete(ArtifactModel).where(ArtifactModel.run_id == run.id))
            session.execute(delete(DbTestRunModel).where(DbTestRunModel.id == run.id))
            session.execute(delete(DbTestCaseModel).where(DbTestCaseModel.id == test_case_id))
            session.execute(delete(ProjectModel).where(ProjectModel.id == project_id))
            session.commit()
        engine.dispose()
