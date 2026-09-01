"""HTTP boundary for deterministic run lifecycle use cases."""

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Any
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from application.generation import SubmitGeneration
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
from auto_at.contracts.execution import ArtifactPolicy, RunStatus, TargetType, TestExecutionResult
from config import Settings, get_settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from infrastructure.artifacts.rustfs import ArtifactStorageError, RustFSArtifactStore
from infrastructure.observability import current_trace_context
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyCatalogRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunReportRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
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
    test_case_name: str | None = None
    target_type: TargetType | None = None
    target_url: str | None = None
    artifact_policy: ArtifactPolicy | None = None
    playwright_test_source: str | None = None
    blocked_external_origins: list[str] = Field(default_factory=list)
    terminal_summary: str | None = None
    created_at: datetime | None = None


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int
    limit: int
    offset: int


class RevisedDraftRequestResponse(BaseModel):
    id: UUID
    correlation_id: UUID
    state: str
    failure_reason: str | None = None


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


class BrowserActionResponse(BaseModel):
    sequence: int
    action: str
    element: str
    duration_ms: int | None = None
    source_line: int | None = None
    has_before_frame: bool = False
    has_after_frame: bool = False


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
                provenance.get("provider") if isinstance(provenance.get("provider"), str) else None
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


def _run_response(
    run: object, created_at: datetime | None = None, test_case_name: str | None = None
) -> RunResponse:
    request = run.request
    runner_config = {} if request is None else request.runner_config
    result_metadata = {} if run.result is None else run.result.runner_metadata
    blocked_external_origins = result_metadata.get("blocked_external_origins", [])
    return RunResponse(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status.value,
        revision=run.revision,
        project_id=run.project_id,
        test_case_id=run.test_case_id,
        test_case_name=test_case_name,
        target_type=None if request is None else request.target_type,
        target_url=None
        if request is None or request.target_url is None
        else str(request.target_url),
        artifact_policy=None if request is None else request.artifact_policy,
        playwright_test_source=(
            runner_config.get("playwright_test_source")
            if isinstance(runner_config.get("playwright_test_source"), str)
            else None
        ),
        blocked_external_origins=(
            [origin for origin in blocked_external_origins if isinstance(origin, str)]
            if isinstance(blocked_external_origins, list)
            else []
        ),
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
    return _run_response(run, test_case_name=test_case.name)


@router.post(
    "/{run_id}/revised-draft",
    response_model=RevisedDraftRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_csrf)],
)
def create_revised_draft(
    run_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RevisedDraftRequestResponse:
    """Queue a reviewable replacement draft; the failed revision remains immutable."""
    with transactional_session(create_session_factory(settings)) as session:
        runs = SqlAlchemyRunRepository(session)
        try:
            run = GetRun(runs).execute(tenant_id, run_id)
            require(
                actor_for_tenant(principal, tenant_id, run.project_id),
                Permission.SUBMIT_GENERATION,
            )
        except (RunNotFoundError, AuthorizationError) as error:
            raise HTTPException(status_code=404, detail="Run not found.") from error
        if run.result is None or run.result.status not in {RunStatus.FAILED, RunStatus.ERRORED}:
            raise HTTPException(
                status_code=409, detail="Only failed or errored runs can be revised."
            )
        if run.request is None or run.request.target_url is None:
            raise HTTPException(status_code=409, detail="Run has no revisable Web UI target.")
        test_case = SqlAlchemyCatalogRepository(session).get_test_case(tenant_id, run.test_case_id)
        source = (
            None if test_case is None else test_case.specification.get("playwright_test_source")
        )
        if not isinstance(source, str) or not source:
            raise HTTPException(
                status_code=409, detail="Run does not reference generated Playwright source."
            )
        report = SqlAlchemyRunReportRepository(session).get_for_run(tenant_id, run.id)
        failure = None if report is None or report.payload is None else report.payload.failure
        failure_detail = failure.message if failure is not None else run.result.summary
        revision_request = (
            "Create a revised replacement for the approved Playwright source below. Preserve its "
            "testing intent, change only what is needed to address the observed deterministic "
            "failure, and keep assertions resilient. This is a reviewable draft, not permission "
            "to change a test verdict.\n\n"
            f"Observed failure: {failure_detail}\n\nApproved source:\n{source}"
        )
        request = SubmitGeneration(
            SqlAlchemyGenerationRepository(session),
            SqlAlchemyAuditEventRepository(session),
            SqlAlchemyOutboxEventRepository(session),
        ).execute(
            tenant_id=tenant_id,
            project_id=run.project_id,
            correlation_id=uuid4(),
            target_url=str(run.request.target_url),
            natural_language_request=revision_request,
            idempotency_key=f"revised-draft:{run.id}:{idempotency_key}",
        )
    return RevisedDraftRequestResponse(
        id=request.id,
        correlation_id=request.correlation_id,
        state=request.state,
        failure_reason=request.failure_reason,
    )


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
        test_case = SqlAlchemyCatalogRepository(session).get_test_case(tenant_id, run.test_case_id)
    return _run_response(run, test_case_name=None if test_case is None else test_case.name)


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
    page = visible[offset : offset + limit]
    with create_session_factory(settings)() as session:
        catalog = SqlAlchemyCatalogRepository(session)
        names = {
            row.run.test_case_id: test_case.name
            for row in page
            if (test_case := catalog.get_test_case(tenant_id, row.run.test_case_id)) is not None
        }
    return RunListResponse(
        items=[
            _run_response(row.run, row.created_at, names.get(row.run.test_case_id)) for row in page
        ],
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
) -> Response:
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
        content = RustFSArtifactStore(settings).read_verified_bytes(
            artifact, settings.artifact_upload_max_bytes
        )
    except (ArtifactStorageError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Artifact integrity check failed.",
        ) from error
    return Response(content=content, media_type=artifact.content_type or "application/octet-stream")


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
        content = RustFSArtifactStore(settings).read_verified_bytes(
            artifact, settings.artifact_upload_max_bytes
        )
        with ZipFile(BytesIO(content)) as archive:
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


def _trace_target_element(node: Any, target: str) -> str | None:
    """Return the most useful safe identifier for one trace-highlighted DOM node."""
    if not isinstance(node, list):
        return None
    if len(node) >= 2 and isinstance(node[0], str) and isinstance(node[1], dict):
        tag, attributes = node[0].lower(), node[1]
        if attributes.get("__playwright_target__") == target:
            label = next(
                (
                    attributes[name]
                    for name in ("aria-label", "title", "name", "data-testid", "id", "alt")
                    if isinstance(attributes.get(name), str) and attributes[name].strip()
                ),
                None,
            )
            if isinstance(label, str):
                return f"{tag} · {label.strip()[:120]}"
            class_name = attributes.get("class")
            if isinstance(class_name, str) and class_name.strip():
                return f"{tag} · .{'.'.join(class_name.split()[:3])}"
            return tag
    for child in node:
        found = _trace_target_element(child, target)
        if found is not None:
            return found
    return None


def _trace_browser_actions(
    path: BytesIO,
) -> tuple[list[BrowserActionResponse], list[tuple[str | None, str | None]]]:
    """Extract a small, read-only click ledger from a verified Playwright trace."""
    with ZipFile(path) as archive:
        trace_name = next(
            (name for name in archive.namelist() if name.endswith("0-trace.trace")), None
        )
        if trace_name is None:
            return [], []
        entry = archive.getinfo(trace_name)
        if entry.file_size > 5_000_000:
            return [], []
        rows = archive.read(trace_name).decode("utf-8", errors="replace").splitlines()
    starts: dict[str, tuple[int, int | None]] = {}
    completed: list[tuple[int, int, int | None, str]] = []
    frames: list[tuple[int, str]] = []
    elements: dict[str, str] = {}
    for row in rows:
        try:
            event = json.loads(row)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        call_id = event.get("callId")
        if event.get("type") == "screencast-frame":
            timestamp, sha1 = event.get("timestamp"), event.get("sha1")
            if isinstance(timestamp, (int, float)) and isinstance(sha1, str):
                frames.append((round(timestamp), sha1))
            continue
        if event.get("type") == "frame-snapshot":
            snapshot = event.get("snapshot")
            if isinstance(snapshot, dict):
                snapshot_call_id = snapshot.get("callId")
                html = snapshot.get("html")
                if isinstance(snapshot_call_id, str):
                    element = _trace_target_element(html, snapshot_call_id)
                    if element is not None:
                        elements[snapshot_call_id] = element
        if not isinstance(call_id, str):
            continue
        if event.get("type") == "before" and event.get("apiName") in {
            "locator.click",
            "elementHandle.click",
        }:
            start = event.get("startTime")
            stack = event.get("stack")
            source_line = None
            if isinstance(stack, list) and stack and isinstance(stack[0], dict):
                line = stack[0].get("line")
                source_line = line if isinstance(line, int) else None
            if isinstance(start, (int, float)):
                starts[call_id] = (round(start), source_line)
        elif event.get("type") == "after" and call_id in starts:
            start, source_line = starts.pop(call_id)
            end = event.get("endTime")
            if isinstance(end, (int, float)):
                completed.append((start, round(end), source_line, call_id))
    frames.sort()
    actions: list[BrowserActionResponse] = []
    action_frames: list[tuple[str | None, str | None]] = []
    for sequence, (start, end, source_line, call_id) in enumerate(completed, start=1):
        before = next((sha1 for timestamp, sha1 in reversed(frames) if timestamp <= start), None)
        after = next((sha1 for timestamp, sha1 in frames if timestamp >= end), None)
        actions.append(
            BrowserActionResponse(
                sequence=sequence,
                action="click",
                element=elements.get(call_id, "button (unlabeled)"),
                duration_ms=end - start,
                source_line=source_line,
                has_before_frame=before is not None,
                has_after_frame=after is not None,
            )
        )
        action_frames.append((before, after))
    return actions, action_frames


def _run_trace_path(evidence: list[object], settings: Settings) -> BytesIO | None:
    trace = next((artifact for artifact in evidence if artifact.uri.lower().endswith(".zip")), None)
    if trace is None:
        return None
    return BytesIO(
        RustFSArtifactStore(settings).read_verified_bytes(trace, settings.artifact_upload_max_bytes)
    )


def _run_evidence(
    run_id: UUID, tenant_id: str, principal: Principal, settings: Settings
) -> list[object]:
    with transactional_session(create_session_factory(settings)) as session:
        try:
            run = GetRun(SqlAlchemyRunRepository(session)).execute(tenant_id, run_id)
            require(actor_for_tenant(principal, tenant_id, run.project_id), Permission.READ)
            return ListArtifacts(SqlAlchemyArtifactRepository(session)).execute(tenant_id, run_id)
        except (RunNotFoundError, AuthorizationError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found."
            ) from error


@router.get("/{run_id}/browser-actions", response_model=list[BrowserActionResponse])
def browser_actions(
    run_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[BrowserActionResponse]:
    try:
        path = _run_trace_path(_run_evidence(run_id, tenant_id, principal, settings), settings)
        return [] if path is None else _trace_browser_actions(path)[0]
    except (BadZipFile, OSError, ValueError):
        return []


@router.get("/{run_id}/browser-actions/{sequence}/frames/{frame}")
def browser_action_frame(
    run_id: UUID,
    sequence: int,
    frame: str,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    if frame not in {"before", "after"} or sequence < 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action frame not found.")
    try:
        path = _run_trace_path(_run_evidence(run_id, tenant_id, principal, settings), settings)
        if path is None:
            raise ValueError("trace is unavailable")
        _, frames = _trace_browser_actions(path)
        before, after = frames[sequence - 1]
        sha1 = before if frame == "before" else after
        if sha1 is None:
            raise ValueError("frame is unavailable")
        with ZipFile(path) as archive:
            image = archive.read(f"resources/{sha1}")
        if len(image) > 3_000_000:
            raise ValueError("frame is too large")
    except (BadZipFile, IndexError, KeyError, OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action frame not found."
        ) from error
    return Response(
        content=image,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


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

    try:
        verified = [
            (
                artifact,
                RustFSArtifactStore(settings).read_verified_bytes(
                    artifact, settings.artifact_upload_max_bytes
                ),
            )
            for artifact in artifacts
        ]
    except (ArtifactStorageError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Artifact integrity check failed.",
        ) from error

    with NamedTemporaryFile(prefix=f"auto-at-run-{run_id}-", suffix=".zip", delete=False) as file:
        archive_path = Path(file.name)
    try:
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            for artifact, content in verified:
                # The generated name is stable, readable, and cannot preserve a storage path.
                suffix = Path(artifact.uri).suffix
                archive.writestr(f"{artifact.kind}-{artifact.id}{suffix}", content)
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
