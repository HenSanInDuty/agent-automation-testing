from uuid import uuid4

from agents.shared.redaction import redact_mapping
from auto_at.contracts.agent import AgentProposal, ApprovalDecision, ProposalKind
from domain.proposals import may_apply_proposal


def test_proposal_requires_matching_explicit_approval() -> None:
    proposal = AgentProposal(
        kind=ProposalKind.HEALING,
        correlation_id=uuid4(),
        summary="Update a locator after human review.",
    )

    assert not may_apply_proposal(proposal, None)
    assert not may_apply_proposal(
        proposal,
        ApprovalDecision(proposal_id=proposal.id, approved=False, decided_by="reviewer"),
    )
    assert may_apply_proposal(
        proposal,
        ApprovalDecision(proposal_id=proposal.id, approved=True, decided_by="reviewer"),
    )


def test_redaction_hides_common_secret_fields() -> None:
    assert redact_mapping({"token": "secret-value", "selector": "#submit"}) == {
        "token": "[REDACTED]",
        "selector": "#submit",
    }
