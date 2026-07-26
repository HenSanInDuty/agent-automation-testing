"""Authorized, read-only operational dashboard data."""

from typing import Annotated

from config import Settings, get_settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from fastapi import APIRouter, Depends, Header, HTTPException, status
from infrastructure.persistence.models import (
    AgentProposalModel,
    ApprovalModel,
    ArtifactModel,
    AuditEventModel,
    ProjectModel,
    TestCaseModel,
    TestRunModel,
)
from infrastructure.persistence.session import create_session_factory
from pydantic import BaseModel
from sqlalchemy import func, select

from api.v1.dependencies.authorization import current_principal

router = APIRouter(prefix="/operations", tags=["operations"])


class OperationsSummary(BaseModel):
    projects: int
    tests: int
    runs: int
    artifacts: int
    proposals: int
    approvals: int
    audit_events: int


@router.get("/summary", response_model=OperationsSummary)
def summary(
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OperationsSummary:
    try:
        require(actor_for_tenant(principal, tenant_id), Permission.READ)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.") from error
    with create_session_factory(settings)() as session:
        return OperationsSummary(
            projects=int(
                session.scalar(
                    select(func.count())
                    .select_from(ProjectModel)
                    .where(ProjectModel.tenant_id == tenant_id)
                )
                or 0
            ),
            tests=int(
                session.scalar(
                    select(func.count())
                    .select_from(TestCaseModel)
                    .where(TestCaseModel.tenant_id == tenant_id)
                )
                or 0
            ),
            runs=int(
                session.scalar(
                    select(func.count())
                    .select_from(TestRunModel)
                    .where(TestRunModel.tenant_id == tenant_id)
                )
                or 0
            ),
            artifacts=int(
                session.scalar(
                    select(func.count())
                    .select_from(ArtifactModel)
                    .where(ArtifactModel.tenant_id == tenant_id)
                )
                or 0
            ),
            proposals=int(
                session.scalar(
                    select(func.count())
                    .select_from(AgentProposalModel)
                    .where(AgentProposalModel.tenant_id == tenant_id)
                )
                or 0
            ),
            approvals=int(
                session.scalar(
                    select(func.count())
                    .select_from(ApprovalModel)
                    .where(ApprovalModel.tenant_id == tenant_id)
                )
                or 0
            ),
            audit_events=int(
                session.scalar(
                    select(func.count())
                    .select_from(AuditEventModel)
                    .where(AuditEventModel.tenant_id == tenant_id)
                )
                or 0
            ),
        )
