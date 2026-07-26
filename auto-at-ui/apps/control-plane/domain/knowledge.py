"""Rules for promoting validated agent suggestions into reusable knowledge."""

from auto_at.contracts.execution import RunStatus, TestExecutionResult

from domain.entities import ApprovalRecord, ProposalRecord


def may_promote_after_rerun(
    proposal: ProposalRecord,
    approval: ApprovalRecord | None,
    rerun: TestExecutionResult | None,
) -> bool:
    """Only an explicit approval plus an independent passing rerun can promote knowledge."""
    return (
        approval is not None
        and approval.tenant_id == proposal.tenant_id
        and approval.proposal_id == proposal.id
        and approval.proposal_version == proposal.proposal_version
        and approval.approved
        and rerun is not None
        and rerun.status is RunStatus.PASSED
        and rerun.run_id != proposal.run_id
        and rerun.correlation_id == proposal.correlation_id
    )
