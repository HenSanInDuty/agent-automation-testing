"""Use cases for immutable, human-reviewed agent proposals."""

from uuid import UUID, uuid4

from domain.entities import ApprovalRecord, ApprovalStateError
from domain.ports import (
    ApprovalRepository,
    AuditEventRepository,
    OutboxEventRepository,
    ProposalRepository,
)
from domain.runs import AuditEvent, OutboxEvent


class ProposalNotFoundError(LookupError):
    pass


class DecideProposal:
    """Record one final human decision; this use case never applies a proposal."""

    def __init__(
        self,
        proposals: ProposalRepository,
        approvals: ApprovalRepository,
        audits: AuditEventRepository,
        outbox: OutboxEventRepository | None = None,
    ) -> None:
        self._proposals = proposals
        self._approvals = approvals
        self._audits = audits
        self._outbox = outbox

    def execute(
        self,
        *,
        tenant_id: str,
        proposal_id: UUID,
        approved: bool,
        decided_by: str,
        reason: str | None,
    ) -> ApprovalRecord:
        proposal = self._proposals.get(tenant_id, proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        if self._approvals.get_final(tenant_id, proposal.id, proposal.proposal_version) is not None:
            raise ApprovalStateError("a proposal version already has a final approval")
        decision = ApprovalRecord.decide(
            proposal, approved=approved, decided_by=decided_by, reason=reason
        )
        self._approvals.add(decision)
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor=decided_by,
                action="proposal.approved" if approved else "proposal.rejected",
                entity_type="agent_proposal",
                entity_id=proposal.id,
                correlation_id=proposal.correlation_id,
            )
        )
        if approved and proposal.payload.get("proposed_change") and self._outbox is not None:
            self._outbox.append(
                OutboxEvent(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    event_type="proposal.review-branch.requested.v1",
                    schema_version="v1",
                    correlation_id=proposal.correlation_id,
                    causation_id=decision.id,
                    idempotency_key=(
                        f"review-branch:{proposal.id}:{proposal.proposal_version}"
                    ),
                    payload={
                        "proposal_id": str(proposal.id),
                        "proposal_version": proposal.proposal_version,
                        "reviewer_id": decided_by,
                    },
                )
            )
        return decision
