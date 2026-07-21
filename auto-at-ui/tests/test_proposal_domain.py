from uuid import uuid4

import pytest
from auto_at.contracts.agent import ProposalKind
from domain.entities import ApprovalRecord, ApprovalStateError, ProposalRecord


def test_only_one_final_approval_is_allowed_for_a_proposal_version() -> None:
    proposal = ProposalRecord.create(
        tenant_id="tenant-a",
        run_id=uuid4(),
        correlation_id=uuid4(),
        kind=ProposalKind.HEALING,
        proposal_version=1,
        summary="Use a resilient accessible locator.",
    )
    approval = ApprovalRecord.decide(proposal, approved=True, decided_by="reviewer")

    assert approval.proposal_id == proposal.id
    assert approval.proposal_version == 1
    with pytest.raises(ApprovalStateError, match="final"):
        ApprovalRecord.decide(proposal, approved=False, decided_by="another-reviewer")
