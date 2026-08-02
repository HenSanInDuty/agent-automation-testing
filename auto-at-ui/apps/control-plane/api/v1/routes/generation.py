"""HTTP boundary for governed generated-test request and review lifecycle."""

from typing import Annotated
from uuid import UUID, uuid4

from application.generation import (
    DecideGeneratedDraft,
    GenerationNotFoundError,
    GenerationStateError,
    SubmitGeneration,
)
from auto_at.contracts.generation import ProjectExecutionPolicy
from config import Settings, get_settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from fastapi import APIRouter, Depends, Header, HTTPException, status
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyRunRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from pydantic import BaseModel, Field

from api.v1.dependencies.authorization import current_principal, current_tenant

router = APIRouter(prefix="/test-generations", tags=["test-generations"])


class SubmitRequest(BaseModel):
    project_id: UUID
    target_url: str = Field(min_length=1, max_length=8_000)
    request: str = Field(min_length=1, max_length=8_000)
    correlation_id: UUID = Field(default_factory=uuid4)


class RequestResponse(BaseModel):
    id: UUID
    project_id: UUID
    correlation_id: UUID
    target_url: str
    redacted_request: str
    request_hash: str
    state: str
    failure_reason: str | None = None
    draft_id: UUID | None = None


class DraftResponse(BaseModel):
    id: UUID
    planning_request_id: UUID
    correlation_id: UUID
    state: str
    title: str
    playwright_test_source: str
    source_hash: str
    assumptions: list[str]
    stop_conditions: list[str]
    provenance: dict[str, object]
    linked_test_case_id: str | None
    linked_run_id: UUID | None


class DecisionRequest(BaseModel):
    approved: bool
    reason: str | None = Field(default=None, max_length=4_000)


class PolicyRequest(BaseModel):
    allowed_origins: list[str] = Field(min_length=1, max_length=100)


def _request_response(
    repository: SqlAlchemyGenerationRepository, request: object
) -> RequestResponse:
    draft = repository.get_draft_for_request(request.tenant_id, request.id)
    return RequestResponse(
        id=request.id,
        project_id=request.project_id,
        correlation_id=request.correlation_id,
        target_url=request.target_url,
        redacted_request=request.redacted_request,
        request_hash=request.request_hash,
        state=request.state,
        failure_reason=request.failure_reason,
        draft_id=None if draft is None else draft.id,
    )


def _draft_response(draft: object) -> DraftResponse:
    return DraftResponse(
        id=draft.id,
        planning_request_id=draft.planning_request_id,
        correlation_id=draft.correlation_id,
        state=draft.state,
        title=draft.title,
        playwright_test_source=draft.playwright_test_source,
        source_hash=draft.source_hash,
        assumptions=draft.assumptions,
        stop_conditions=draft.stop_conditions,
        provenance=draft.provenance,
        linked_test_case_id=draft.linked_test_case_id,
        linked_run_id=draft.linked_run_id,
    )


@router.put("/projects/{project_id}/policy", response_model=PolicyRequest)
def set_policy(
    project_id: UUID,
    payload: PolicyRequest,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PolicyRequest:
    try:
        normalized = ProjectExecutionPolicy(
            project_id=project_id, allowed_origins=payload.allowed_origins
        ).allowed_origins
        require(actor_for_tenant(principal, tenant_id, project_id), Permission.MANAGE_PROJECT)
    except (ValueError, AuthorizationError) as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error
    with transactional_session(create_session_factory(settings)) as session:
        SqlAlchemyGenerationRepository(session).set_policy(tenant_id, project_id, normalized)
    return PolicyRequest(allowed_origins=normalized)


@router.post("", response_model=RequestResponse, status_code=status.HTTP_202_ACCEPTED)
def submit(
    payload: SubmitRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RequestResponse:
    try:
        require(
            actor_for_tenant(principal, tenant_id, payload.project_id), Permission.SUBMIT_GENERATION
        )
        with transactional_session(create_session_factory(settings)) as session:
            repository = SqlAlchemyGenerationRepository(session)
            request = SubmitGeneration(
                repository,
                SqlAlchemyAuditEventRepository(session),
                SqlAlchemyOutboxEventRepository(session),
            ).execute(
                tenant_id=tenant_id,
                project_id=payload.project_id,
                correlation_id=payload.correlation_id,
                target_url=payload.target_url,
                natural_language_request=payload.request,
                idempotency_key=idempotency_key,
            )
            return _request_response(repository, request)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error
    except (ValueError, GenerationStateError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/requests/{request_id}", response_model=RequestResponse)
def get_request(
    request_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RequestResponse:
    with create_session_factory(settings)() as session:
        repository = SqlAlchemyGenerationRepository(session)
        request = repository.get_request(tenant_id, request_id)
        try:
            if request is None:
                raise GenerationNotFoundError(request_id)
            require(actor_for_tenant(principal, tenant_id, request.project_id), Permission.READ)
        except (GenerationNotFoundError, AuthorizationError) as error:
            raise HTTPException(status_code=404, detail="Generation request not found.") from error
        return _request_response(repository, request)


@router.get("/drafts/{draft_id}", response_model=DraftResponse)
def get_draft(
    draft_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    with create_session_factory(settings)() as session:
        repository = SqlAlchemyGenerationRepository(session)
        draft = repository.get_draft(tenant_id, draft_id)
        request = (
            None if draft is None else repository.get_request(tenant_id, draft.planning_request_id)
        )
        try:
            if request is None:
                raise GenerationNotFoundError(draft_id)
            require(actor_for_tenant(principal, tenant_id, request.project_id), Permission.READ)
        except (GenerationNotFoundError, AuthorizationError) as error:
            raise HTTPException(status_code=404, detail="Generated draft not found.") from error
        return _draft_response(draft)


@router.post("/drafts/{draft_id}/decision", response_model=DraftResponse)
def decide(
    draft_id: UUID,
    payload: DecisionRequest,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    with transactional_session(create_session_factory(settings)) as session:
        repository = SqlAlchemyGenerationRepository(session)
        draft = repository.get_draft(tenant_id, draft_id)
        request = (
            None if draft is None else repository.get_request(tenant_id, draft.planning_request_id)
        )
        try:
            if request is None:
                raise GenerationNotFoundError(draft_id)
            actor = actor_for_tenant(principal, tenant_id, request.project_id)
            require(actor, Permission.DECIDE_GENERATION)
            decided, _ = DecideGeneratedDraft(
                repository,
                SqlAlchemyAuditEventRepository(session),
                SqlAlchemyOutboxEventRepository(session),
                SqlAlchemyRunRepository(session),
            ).execute(
                tenant_id=tenant_id,
                draft_id=draft_id,
                approved=payload.approved,
                decided_by=actor.subject,
                reason=payload.reason,
            )
        except (GenerationNotFoundError, AuthorizationError) as error:
            raise HTTPException(status_code=404, detail="Generated draft not found.") from error
        except GenerationStateError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    return _draft_response(decided)
