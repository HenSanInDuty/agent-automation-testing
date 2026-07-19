from auto_at.contracts.agent import AgentProposal, ApprovalDecision


def may_apply_proposal(proposal: AgentProposal, decision: ApprovalDecision | None) -> bool:
    """Only an explicit approval can authorize a proposed agent change."""
    return decision is not None and decision.proposal_id == proposal.id and decision.approved
