"""HTTP boundary for deterministic run lifecycle use cases."""

from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from application.reporting import GetRunReport
from application.runs import (
    CancelRun,
    CreateRun,
    CreateRunCommand,
    GetRun,
    ListArtifacts,
    RecordDeterministicResult,
    RequestFailureTriage,
    RunNotFoundError,
)
from auto_at.contracts.execution import ArtifactPolicy, TargetType, TestExecutionResult
from config import Settings, get_settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from infrastructure.observability import current_trace_context
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyCatalogRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunReportRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from infrastructure.runners import VerifiedLocalArtifactPort
from pydantic import BaseModel, Field

from api.v1.dependencies.authorization import current_principal, current_tenant, require_csrf

router = APIRouter(prefix="/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    project_id: UUID
    test_case_id: str = Field(min_length=1, max_length=200)
    revision: str | None = Field(default=None, min_length=7, max_length=128)
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
    project_id: UUID | None = None
    test_case_id: str | None = None
    target_type: TargetType | None = None
    target_url: str | None = None
    artifact_policy: ArtifactPolicy | None = None
    terminal_summary: str | None = None
    created_at: datetime | None = None


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int
    limit: int
    offset: int


class ArtifactResponse(BaseModel):
    id: UUID
    kind: str
    uri: str
    checksum: str
    size: int
    content_type: str | None = None


class ArchiveEntryResponse(BaseModel):
    path: str
    size: int
    is_directory: bool


class RunReportObservationResponse(BaseModel):
    text: str
    evidence_references: list[str]


class RunReportFailureResponse(BaseModel):
    stage: str
    location: str
    message: str
    evidence_references: list[str]


class RunReportPayloadResponse(BaseModel):
    deterministic_status: str
    headline: str
    what_ran: str
    observations: list[RunReportObservationResponse]
    failure: RunReportFailureResponse | None
    unverified_or_skipped: list[str]
    limitations: list[str]


class RunReportProvenanceResponse(BaseModel):
    provider: str | None = None
    model: str | None = None
    redaction_policy_version: str | None = None
    input_hash: str


class RunReportResponse(BaseModel):
    report_version: int
    schema_version: str
    prompt_version: str
    deterministic_status: str
    status: str
    payload: RunReportPayloadResponse | None
    unavailable_reason: str | None = None
    provenance: RunReportProvenanceResponse
    created_at: datetime


def _run_report_response(report: object) -> RunReportResponse:
    payload = report.payload
    provenance = report.provenance
    safe_reason = provenance.get("safe_reason")
    return RunReportResponse(
        report_version=report.report_version,
        schema_version=report.schema_version,
        prompt_version=report.prompt_version,
        deterministic_status=report.deterministic_status.value,
        status=report.status.value,
        payload=(
            None
            if payload is None
            else RunReportPayloadResponse.model_validate(payload.model_dump())
        ),
        unavailable_reason=safe_reason if isinstance(safe_reason, str) else None,
        provenance=RunReportProvenanceResponse(
            provider=(
                provenance.get("provider")
                if isinstance(provenance.get("provider"), str)
                else None
            ),
            model=provenance.get("model") if isinstance(provenance.get("model"), str) else None,
            redaction_policy_version=(
                provenance.get("redaction_policy_version")
                if isinstance(provenance.get("redaction_policy_version"), str)
                else None
            ),
            input_hash=report.input_hash,
        ),
        created_at=report.created_at,
    )


def _run_response(run: object, created_at: datetime | None = None) -> RunResponse:
    request = run.request
    return RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
        project_id=run.project_id,
        test_case_id=run.test_case_id,
        target_type=None if request is None else request.target_type,
        target_url=None
        if request is None or request.target_url is None
        else str(request.target_url),
        artifact_policy=None if request is None else request.artifact_policy,
        terminal_summary=None if run.result is None else run.result.summary,
        created_at=created_at,
    )


@router.post(
    "",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_run(
    payload: CreateRunRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    """Create a queued run and requested outbox event in one database transaction."""
    try:
        require(actor_for_tenant(principal, tenant_id, payload.project_id), Permission.CREATE_RUN)
    except AuthorizationError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        ) from error
    with create_session_factory(settings)() as session:
        test_case = SqlAlchemyCatalogRepository(session).get_test_case(
            tenant_id, payload.test_case_id
        )
    if test_case is None or test_case.project_id != payload.project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found.")
    if payload.revision is not None and payload.revision != test_case.revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Test case revision is immutable."
        )
    if payload.target_type != test_case.target_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target type must match the test case.",
        )
    trace = current_trace_context()
    runner_config = dict(payload.runner_config)
    if trace is not None:
        runner_config["traceparent"] = trace.traceparent()
    with transactional_session(create_session_factory(settings)) as session:
        run = CreateRun(
            SqlAlchemyRunRepository(session),
            SqlAlchemyOutboxEventRepository(session),
            SqlAlchemyAuditEventRepository(session),
            SqlAlchemyActivityEventRepository(session),
        ).execute(
            CreateRunCommand(
                tenant_id=tenant_id,
                project_id=payload.project_id,
                test_case_id=payload.test_case_id,
                revision=test_case.revision,
                correlation_id=payload.correlation_id,
                idempotency_key=idempotency_key,
                target_type=payload.target_type,
                target_url=payload.target_url,
                runner_config=runner_config,
                artifact_policy=payload.artifact_policy,
            )
        )
    # UI creation is always asynchronous: the outbox publisher starts the durable
    # workflow after this transaction commits. The runner remains verdict authority.
    return _run_response(run)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    with create_session_factory(settings)() as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        try:
            require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
        except AuthorizationError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
    return _run_response(run)


@router.get("/{run_id}/report", response_model=RunReportResponse)
def get_run_report(
    run_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunReportResponse:
    """Return a report only after the caller has passed the run's normal read boundary."""
    with create_session_factory(settings)() as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
        except (RunNotFoundError, AuthorizationError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run report not found."
            ) from error
        report = GetRunReport(SqlAlchemyRunReportRepository(session)).execute(tenant_id, run_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run report not found.")
    return _run_report_response(report)


@router.get("", response_model=RunListResponse)
def list_runs(
    project_id: UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    target_type: TargetType | None = None,
    revision: Annotated[str | None, Query(max_length=128)] = None,
    correlation_id: UUID | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    tenant_id: Annotated[str, Depends(current_tenant)] = "",
    principal: Annotated[Principal, Depends(current_principal)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> RunListResponse:
    with create_session_factory(settings)() as session:
        rows = SqlAlchemyRunRepository(session).list(tenant_id)
    visible = []
    for row in rows:
        try:
            require(actor_for_tenant(principal, tenant_id, row.run.project_id), Permission.READ)
        except AuthorizationError:
            continue
        request = row.run.request
        if project_id is not None and row.run.project_id != project_id:
            continue
        if status_filter is not None and row.run.status.value != status_filter:
            continue
        if target_type is not None and (request is None or request.target_type != target_type):
            continue
        if revision is not None and row.run.revision != revision:
            continue
        if correlation_id is not None and row.run.correlation_id != correlation_id:
            continue
        if started_after is not None and row.created_at < started_after:
            continue
        if started_before is not None and row.created_at > started_before:
            continue
        visible.append(row)
    return RunListResponse(
        items=[_run_response(row.run, row.created_at) for row in visible[offset : offset + limit]],
        total=len(visible),
        limit=limit,
        offset=offset,
    )


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(
    run_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    """Persist a cancellation command and deliver it through the outbox."""
    with transactional_session(create_session_factory(settings)) as session:
        try:
            existing_run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(
                actor_for_tenant(principal, tenant_id, existing_run.project_id),
                Permission.CANCEL_RUN,
            )
            run = CancelRun(
                SqlAlchemyRunRepository(session),
                SqlAlchemyOutboxEventRepository(session),
                SqlAlchemyAuditEventRepository(session),
                SqlAlchemyActivityEventRepository(session),
            ).execute(tenant_id, run_id, idempotency_key)
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        except AuthorizationError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Run cannot be cancelled."
            ) from error
    return _run_response(run)


@router.get("/{run_id}/artifacts", response_model=list[ArtifactResponse])
def list_artifacts(
    run_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[ArtifactResponse]:
    with create_session_factory(settings)() as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
        except (RunNotFoundError, AuthorizationError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
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
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    with create_session_factory(settings)() as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
        except (RunNotFoundError, AuthorizationError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
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


@router.get(
    "/{run_id}/artifacts/{artifact_id}/archive-entries",
    response_model=list[ArchiveEntryResponse],
)
def list_artifact_archive_entries(
    run_id: UUID,
    artifact_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[ArchiveEntryResponse]:
    """Return bounded, non-extracted contents of one verified ZIP artifact."""
    with create_session_factory(settings)() as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
        except (RunNotFoundError, AuthorizationError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        artifacts = ListArtifacts(SqlAlchemyArtifactRepository(session)).execute(tenant_id, run_id)
    artifact = next((item for item in artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    try:
        path = VerifiedLocalArtifactPort(settings.artifact_root).verified_path(artifact)
        with ZipFile(path) as archive:
            entries = archive.infolist()
    except (BadZipFile, OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Artifact is not a readable ZIP archive.",
        ) from error
    if len(entries) > 2_000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Archive contains too many entries to preview.",
        )
    return [
        ArchiveEntryResponse(
            path=entry.filename,
            size=entry.file_size,
            is_directory=entry.is_dir(),
        )
        for entry in entries
    ]


@router.get("/{run_id}/artifacts.zip")
def download_artifact_archive(
    run_id: UUID,
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    """Download all retained evidence as one verified ZIP archive."""
    with create_session_factory(settings)() as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
        except (RunNotFoundError, AuthorizationError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        artifacts = ListArtifacts(SqlAlchemyArtifactRepository(session)).execute(tenant_id, run_id)
    if not artifacts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No artifacts found.")

    artifact_port = VerifiedLocalArtifactPort(settings.artifact_root)
    try:
        verified = [(artifact, artifact_port.verified_path(artifact)) for artifact in artifacts]
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Artifact integrity check failed.",
        ) from error

    with NamedTemporaryFile(prefix=f"auto-at-run-{run_id}-", suffix=".zip", delete=False) as file:
        archive_path = Path(file.name)
    try:
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            for artifact, path in verified:
                # The generated name is stable, readable, and cannot preserve a storage path.
                archive.write(path, arcname=f"{artifact.kind}-{artifact.id}{path.suffix}")
    except OSError as error:
        archive_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to prepare artifact archive.",
        ) from error
    background_tasks.add_task(archive_path.unlink, missing_ok=True)
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"run-{run_id}-artifacts.zip",
        background=background_tasks,
    )


@router.post("/{run_id}/result", response_model=RunResponse)
def record_result(
    run_id: UUID,
    payload: TestExecutionResult,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    if payload.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Run ID mismatch.",
        )
    with transactional_session(create_session_factory(settings)) as session:
        try:
            existing_run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(
                actor_for_tenant(principal, tenant_id, existing_run.project_id),
                Permission.CREATE_RUN,
            )
            run = RecordDeterministicResult(SqlAlchemyRunRepository(session)).execute(
                tenant_id, payload
            )
            RequestFailureTriage(
                SqlAlchemyOutboxEventRepository(session), SqlAlchemyAuditEventRepository(session)
            ).execute(run)
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error
        except AuthorizationError as error:
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
