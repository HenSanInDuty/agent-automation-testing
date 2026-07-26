from uuid import uuid4

import pytest
from application.proposals import DecideProposal
from auto_at.contracts.agent import ProposalKind
from domain.entities import ApprovalStateError, ProposalRecord


class Proposals:
    def __init__(self, proposal: ProposalRecord) -> None:
        self.proposal = proposal

    def get(self, tenant_id: str, proposal_id: object) -> ProposalRecord | None:
        return (
            self.proposal
            if (tenant_id, proposal_id) == (self.proposal.tenant_id, self.proposal.id)
            else None
        )


class Approvals:
    def __init__(self) -> None:
        self.items = []

    def get_final(
        self, tenant_id: str, proposal_id: object, proposal_version: int
    ) -> object | None:
        return next(iter(self.items), None)

    def add(self, approval: object) -> None:
        self.items.append(approval)


class Audits:
    def __init__(self) -> None:
        self.items = []

    def append(self, audit: object) -> None:
        self.items.append(audit)


class Outbox:
    def __init__(self) -> None:
        self.items = []

    def append(self, event: object) -> None:
        self.items.append(event)


def test_decision_is_immutable_and_does_not_apply_a_proposal() -> None:
    proposal = ProposalRecord.create(
        tenant_id="tenant-a",
        run_id=uuid4(),
        correlation_id=uuid4(),
        kind=ProposalKind.HEALING,
        proposal_version=1,
        summary="Suggest a locator update.",
    )
    approvals = Approvals()
    audits = Audits()
    use_case = DecideProposal(Proposals(proposal), approvals, audits)
    decision = use_case.execute(
        tenant_id="tenant-a",
        proposal_id=proposal.id,
        approved=False,
        decided_by="reviewer",
        reason="Evidence is insufficient.",
    )
    assert not decision.approved
    assert decision.reason == "Evidence is insufficient."
    assert len(audits.items) == 1
    with pytest.raises(ApprovalStateError):
        use_case.execute(
            tenant_id="tenant-a",
            proposal_id=proposal.id,
            approved=True,
            decided_by="reviewer",
            reason="Changed mind.",
        )


def test_approved_change_requests_a_review_branch_without_applying_it() -> None:
    proposal = ProposalRecord.create(
        tenant_id="tenant-a",
        run_id=uuid4(),
        correlation_id=uuid4(),
        kind=ProposalKind.HEALING,
        proposal_version=1,
        summary="Suggest a locator update.",
        payload={"proposed_change": {"locator": "[data-testid=save]"}},
    )
    outbox = Outbox()

    decision = DecideProposal(Proposals(proposal), Approvals(), Audits(), outbox).execute(
        tenant_id="tenant-a",
        proposal_id=proposal.id,
        approved=True,
        decided_by="reviewer",
        reason="Create a review branch.",
    )

    assert decision.approved
    assert len(outbox.items) == 1
    assert outbox.items[0].event_type == "proposal.review-branch.requested.v1"
