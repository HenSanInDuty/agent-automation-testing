"""HTTP boundary for deterministic run lifecycle use cases."""

from typing import Annotated
from uuid import UUID, uuid4

from application.runs import (
    CancelRun,
    CreateRun,
    CreateRunCommand,
    DispatchRun,
    GetRun,
    ListArtifacts,
    RecordDeterministicResult,
    RunNotFoundError,
)
from auto_at.contracts.execution import (
    ArtifactPolicy,
    TargetType,
    TestExecutionRequest,
    TestExecutionResult,
)
from config import Settings, get_settings
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import FileResponse
from infrastructure.persistence.repositories import (
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from infrastructure.runners import (
    HttpPlaywrightTransport,
    RunnerUnavailableError,
    VerifiedLocalArtifactPort,
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    project_id: UUID
    test_case_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=7, max_length=128)
    correlation_id: UUID = Field(default_factory=uuid4)
    target_type: TargetType = TargetType.WEB_UI
    target_url: str | None = None
    runner_config: dict[str, object] = Field(default_factory=dict)
    artifact_policy: ArtifactPolicy = Field(default_factory=ArtifactPolicy)


class RunResponse(BaseModel):
    id: UUID
    correlation_id: UUID
    status: str
    revision: str


class ArtifactResponse(BaseModel):
    id: UUID
    kind: str
    uri: str
    checksum: str
    size: int
    content_type: str | None = None


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: CreateRunRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    """Create a queued run and requested outbox event in one database transaction."""
    with transactional_session(create_session_factory(settings)) as session:
        run = CreateRun(
            SqlAlchemyRunRepository(session),
            SqlAlchemyOutboxEventRepository(session),
            SqlAlchemyAuditEventRepository(session),
        ).execute(
            CreateRunCommand(
                tenant_id=tenant_id,
                project_id=payload.project_id,
                test_case_id=payload.test_case_id,
                revision=payload.revision,
                correlation_id=payload.correlation_id,
                idempotency_key=idempotency_key,
                target_type=payload.target_type,
                target_url=payload.target_url,
                runner_config=payload.runner_config,
                artifact_policy=payload.artifact_policy,
            )
        )
    response = RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
    )
    if not settings.runner_dispatch_enabled:
        return response
    if payload.target_type != TargetType.WEB_UI:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only web_ui is available.",
        )
    try:
        with transactional_session(create_session_factory(settings)) as session:
            runs = SqlAlchemyRunRepository(session)
            artifacts = SqlAlchemyArtifactRepository(session)
            dispatched_run, result = DispatchRun(
                runs, HttpPlaywrightTransport(settings.playwright_worker_url)
            ).execute(
                tenant_id,
                TestExecutionRequest(
                    run_id=run.id,
                    correlation_id=run.correlation_id,
                    project_id=run.project_id,
                    test_case_id=run.test_case_id,
                    target_type=payload.target_type,
                    target_url=payload.target_url,
                    revision=run.revision,
                    runner_config=payload.runner_config,
                    artifact_policy=payload.artifact_policy,
                ),
            )
            VerifiedLocalArtifactPort(settings.artifact_root, artifacts).persist_result_artifacts(
                tenant_id, result, payload.artifact_policy.retain_days
            )
            runs.save_result(dispatched_run, result)
        return RunResponse(
            id=run.id,
            correlation_id=run.correlation_id,
            status=result.status.value,
            revision=run.revision,
        )
    except RunnerUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Playwright worker unavailable.",
        ) from error


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: UUID,
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    with create_session_factory(settings)() as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
    return RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
    )


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(
    run_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    """Persist a cancellation command and deliver it through the outbox."""
    with transactional_session(create_session_factory(settings)) as session:
        try:
            run = CancelRun(
                SqlAlchemyRunRepository(session),
                SqlAlchemyOutboxEventRepository(session),
                SqlAlchemyAuditEventRepository(session),
            ).execute(tenant_id, run_id, idempotency_key)
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Run cannot be cancelled."
            ) from error
    return RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
    )


@router.get("/{run_id}/artifacts", response_model=list[ArtifactResponse])
def list_artifacts(
    run_id: UUID,
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[ArtifactResponse]:
    with create_session_factory(settings)() as session:
        artifacts = ListArtifacts(SqlAlchemyArtifactRepository(session)).execute(tenant_id, run_id)
    return [
        ArtifactResponse(
            id=artifact.id,
            kind=artifact.kind,
            uri=artifact.uri,
            checksum=artifact.checksum,
            size=artifact.size,
            content_type=artifact.content_type,
        )
        for artifact in artifacts
    ]


@router.get("/{run_id}/artifacts/{artifact_id}")
def download_artifact(
    run_id: UUID,
    artifact_id: UUID,
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    with create_session_factory(settings)() as session:
        artifacts = ListArtifacts(SqlAlchemyArtifactRepository(session)).execute(tenant_id, run_id)
    artifact = next((item for item in artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    try:
        path = VerifiedLocalArtifactPort(settings.artifact_root).verified_path(artifact)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Artifact integrity check failed.",
        ) from error
    return FileResponse(path, media_type=artifact.content_type or "application/octet-stream")


@router.post("/{run_id}/result", response_model=RunResponse)
def record_result(
    run_id: UUID,
    payload: TestExecutionResult,
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    if payload.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Run ID mismatch.",
        )
    with transactional_session(create_session_factory(settings)) as session:
        try:
            run = RecordDeterministicResult(SqlAlchemyRunRepository(session)).execute(
                tenant_id, payload
            )
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Run already has a different terminal result.",
            ) from error
    return RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
    )
