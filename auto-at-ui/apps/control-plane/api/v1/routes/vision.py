"""HTTP boundary for governed, advisory visual exploration."""

from typing import Annotated
from uuid import UUID, uuid4

from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, AgentRuntimeConfig
from application.vision import SubmitVisualExploration, VisionStateError
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
    SqlAlchemyActivityEventRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyCatalogRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyVisionRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from pydantic import BaseModel, ConfigDict, Field

from api.v1.dependencies.authorization import current_principal, current_tenant

router = APIRouter(prefix="/vision", tags=["vision"])


class VisionPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    provider: str
    model: str
    raw_screenshot_transfer_accepted: bool
    max_steps: int
    max_screenshot_bytes: int
    max_session_seconds: int
    max_cost_usd: float
    max_requests_per_minute: int


class SubmitExplorationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID
    correlation_id: UUID = Field(default_factory=uuid4)
    target_url: str = Field(min_length=1, max_length=2_000)
    task_intent: str = Field(min_length=1, max_length=4_000)
    use_vision: bool


class ExplorationResponse(BaseModel):
    id: UUID
    project_id: UUID
    correlation_id: UUID
    state: str
    policy_version: str
    provider: str
    model: str
    max_steps: int
    max_hops: int
    max_states: int
    max_screenshot_bytes: int
    max_session_seconds: int
    safe_failure_reason: str | None


class VisualActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int
    action: dict[str, object]
    evidence_checksum: str | None


class ExplorationListResponse(BaseModel):
    items: list[ExplorationResponse]
    total: int


def _runtime(
    settings: Settings, configs: SqlAlchemyConfigurationRepository, tenant_id: str
) -> AgentRuntimeConfig:
    return AgentRuntimeConfig.from_settings(settings).with_override(
        configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY)
    )


def _policy_response(runtime: AgentRuntimeConfig) -> VisionPolicyResponse:
    return VisionPolicyResponse.model_validate(runtime.vision.model_dump())


def _response(record: object) -> ExplorationResponse:
    return ExplorationResponse(
        id=record.id,
        project_id=record.project_id,
        correlation_id=record.correlation_id,
        state=record.state,
        policy_version=record.policy_version,
        provider=record.provider,
        model=record.model,
        max_steps=record.max_steps,
        max_hops=record.max_hops,
        max_states=record.max_states,
        max_screenshot_bytes=record.max_screenshot_bytes,
        max_session_seconds=record.max_session_seconds,
        safe_failure_reason=record.safe_failure_reason,
    )


@router.get("/policy", response_model=VisionPolicyResponse)
def get_policy(
    tenant_id: Annotated[str, Depends(current_tenant)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VisionPolicyResponse:
    with create_session_factory(settings)() as session:
        configs = SqlAlchemyConfigurationRepository(session)
        return _policy_response(_runtime(settings, configs, tenant_id))


@router.put("/policy", response_model=VisionPolicyResponse)
def set_policy(
    payload: VisionPolicyResponse,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VisionPolicyResponse:
    try:
        require(actor_for_tenant(principal, tenant_id), Permission.MANAGE_TENANT)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Tenant not found.") from error
    with transactional_session(create_session_factory(settings)) as session:
        configs = SqlAlchemyConfigurationRepository(session)
        merged = _runtime(settings, configs, tenant_id).model_dump()
        merged["vision"] = payload.model_dump()
        updated = AgentRuntimeConfig.model_validate(merged)
        configs.set(tenant_id, AGENT_RUNTIME_CONFIG_KEY, updated.model_dump())
    return _policy_response(updated)


@router.post(
    "/explorations", response_model=ExplorationResponse, status_code=status.HTTP_202_ACCEPTED
)
def submit_exploration(
    payload: SubmitExplorationRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExplorationResponse:
    if not payload.use_vision:
        raise HTTPException(status_code=422, detail="use_vision must be true for this endpoint")
    try:
        require(
            actor_for_tenant(principal, tenant_id, payload.project_id),
            Permission.SUBMIT_GENERATION,
        )
        with transactional_session(create_session_factory(settings)) as session:
            configs = SqlAlchemyConfigurationRepository(session)
            record = SubmitVisualExploration(
                SqlAlchemyVisionRepository(session),
                configs,
                SqlAlchemyCatalogRepository(session),
                SqlAlchemyGenerationRepository(session),
                SqlAlchemyAuditEventRepository(session),
                SqlAlchemyActivityEventRepository(session),
                SqlAlchemyOutboxEventRepository(session),
            ).execute(
                tenant_id=tenant_id,
                project_id=payload.project_id,
                correlation_id=payload.correlation_id,
                target_url=payload.target_url,
                task_intent=payload.task_intent,
                idempotency_key=idempotency_key,
                runtime=_runtime(settings, configs, tenant_id),
                actor=principal.subject,
                intent_encryption_key=settings.vision_intent_encryption_key,
                intent_retention_days=settings.vision_intent_retention_days,
            )
            return _response(record)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error
    except VisionStateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/explorations/{session_id}", response_model=ExplorationResponse)
def get_exploration(
    session_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExplorationResponse:
    with create_session_factory(settings)() as session:
        record = SqlAlchemyVisionRepository(session).get(tenant_id, session_id)
        try:
            if record is None:
                raise AuthorizationError("missing")
            require(actor_for_tenant(principal, tenant_id, record.project_id), Permission.READ)
        except AuthorizationError as error:
            raise HTTPException(status_code=404, detail="Visual exploration not found.") from error
        return _response(record)


@router.get("/explorations/{session_id}/actions", response_model=list[VisualActionResponse])
def list_actions(
    session_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[VisualActionResponse]:
    with create_session_factory(settings)() as session:
        repository = SqlAlchemyVisionRepository(session)
        record = repository.get(tenant_id, session_id)
        try:
            if record is None:
                raise AuthorizationError("missing")
            require(actor_for_tenant(principal, tenant_id, record.project_id), Permission.READ)
        except AuthorizationError as error:
            raise HTTPException(status_code=404, detail="Visual exploration not found.") from error
        return [
            VisualActionResponse(
                sequence=action.sequence,
                action=action.action,
                evidence_checksum=action.evidence_checksum,
            )
            for action in repository.list_actions(tenant_id, session_id)
        ]


@router.get("/explorations", response_model=ExplorationListResponse)
def list_explorations(
    project_id: UUID | None = None,
    tenant_id: Annotated[str, Depends(current_tenant)] = "",
    principal: Annotated[Principal, Depends(current_principal)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> ExplorationListResponse:
    with create_session_factory(settings)() as session:
        records = SqlAlchemyVisionRepository(session).list(tenant_id, project_id)
        visible = []
        for record in records:
            try:
                require(actor_for_tenant(principal, tenant_id, record.project_id), Permission.READ)
            except AuthorizationError:
                continue
            visible.append(_response(record))
    return ExplorationListResponse(items=visible, total=len(visible))
