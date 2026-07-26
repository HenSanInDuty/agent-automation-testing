"""Human-only proposal approval boundary."""

from typing import Annotated
from uuid import UUID

from application.proposals import DecideProposal, ProposalNotFoundError
from config import Settings, get_settings
from domain.entities import ApprovalStateError
from fastapi import APIRouter, Depends, Header, HTTPException, status
from infrastructure.persistence.repositories import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyProposalRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from pydantic import BaseModel, Field

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalDecisionRequest(BaseModel):
    approved: bool
    reason: str | None = Field(default=None, max_length=4_000)


class ProposalDecisionResponse(BaseModel):
    proposal_id: UUID
    proposal_version: int
    approved: bool
    decided_by: str
    reason: str | None


class ProposalResponse(BaseModel):
    id: UUID
    run_id: UUID
    correlation_id: UUID
    kind: str
    proposal_version: int
    summary: str
    payload: dict[str, object]


@router.get("/{proposal_id}", response_model=ProposalResponse)
def get_proposal(
    proposal_id: UUID,
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProposalResponse:
    with transactional_session(create_session_factory(settings)) as session:
        proposal = SqlAlchemyProposalRepository(session).get(tenant_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")
    return ProposalResponse(
        id=proposal.id,
        run_id=proposal.run_id,
        correlation_id=proposal.correlation_id,
        kind=proposal.kind.value,
        proposal_version=proposal.proposal_version,
        summary=proposal.summary,
        payload=proposal.payload,
    )


@router.post("/{proposal_id}/decision", response_model=ProposalDecisionResponse)
def decide_proposal(
    proposal_id: UUID,
    payload: ProposalDecisionRequest,
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    reviewer_id: Annotated[str, Header(alias="X-Reviewer-Id", min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProposalDecisionResponse:
    with transactional_session(create_session_factory(settings)) as session:
        try:
            decision = DecideProposal(
                SqlAlchemyProposalRepository(session),
                SqlAlchemyApprovalRepository(session),
                SqlAlchemyAuditEventRepository(session),
                SqlAlchemyOutboxEventRepository(session),
            ).execute(
                tenant_id=tenant_id,
                proposal_id=proposal_id,
                approved=payload.approved,
                decided_by=reviewer_id,
                reason=payload.reason,
            )
        except ProposalNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found."
            ) from error
        except ApprovalStateError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Proposal version already has a final decision.",
            ) from error
    return ProposalDecisionResponse(
        proposal_id=decision.proposal_id,
        proposal_version=decision.proposal_version,
        approved=decision.approved,
        decided_by=decision.decided_by,
        reason=decision.reason,
    )
