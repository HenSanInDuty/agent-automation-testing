from uuid import uuid4

from auto_at.contracts.agent import ProposalKind
from auto_at.contracts.execution import RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from domain.entities import ApprovalRecord, ProposalRecord
from domain.knowledge import may_promote_after_rerun


def result(run_id, correlation_id, status: RunStatus) -> ExecutionResult:
    return ExecutionResult(
        run_id=run_id,
        correlation_id=correlation_id,
        status=status,
        started_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:00:01Z",
        summary="rerun",
    )


def test_promotion_requires_approval_and_an_independent_passing_rerun() -> None:
    proposal = ProposalRecord.create(
        tenant_id="tenant-a",
        run_id=uuid4(),
        correlation_id=uuid4(),
        kind=ProposalKind.HEALING,
        proposal_version=1,
        summary="Update locator.",
    )
    approval = ApprovalRecord.decide(proposal, approved=True, decided_by="reviewer")

    assert not may_promote_after_rerun(
        proposal, approval, result(proposal.run_id, proposal.correlation_id, RunStatus.PASSED)
    )
    assert not may_promote_after_rerun(
        proposal, approval, result(uuid4(), proposal.correlation_id, RunStatus.FAILED)
    )
    assert may_promote_after_rerun(
        proposal, approval, result(uuid4(), proposal.correlation_id, RunStatus.PASSED)
    )
