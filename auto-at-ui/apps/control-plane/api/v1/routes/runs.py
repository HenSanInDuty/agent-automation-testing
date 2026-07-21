"""HTTP boundary for deterministic run lifecycle use cases."""

from typing import Annotated
from uuid import UUID, uuid4

from application.runs import (
    CreateRun,
    CreateRunCommand,
    GetRun,
    ListArtifacts,
    RecordDeterministicResult,
    RunNotFoundError,
)
from auto_at.contracts.execution import TestExecutionResult
from config import Settings, get_settings
from fastapi import APIRouter, Depends, Header, HTTPException, status
from infrastructure.persistence.repositories import (
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from pydantic import BaseModel, Field

router = APIRouter(prefix="/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    project_id: UUID
    test_case_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=7, max_length=128)
    correlation_id: UUID = Field(default_factory=uuid4)


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
            )
        )
    return RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
    )


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
        )
        for artifact in artifacts
    ]


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
    return RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
    )
