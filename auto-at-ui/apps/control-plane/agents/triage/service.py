from auto_at.contracts.agent import AgentProposal, ProposalKind
from auto_at.contracts.execution import TestExecutionResult


def propose_failure_triage(result: TestExecutionResult) -> AgentProposal:
    """Create a reviewable triage record; model invocation belongs behind this boundary."""
    return AgentProposal(
        kind=ProposalKind.TRIAGE,
        correlation_id=result.correlation_id,
        summary=f"Triage requested for deterministic {result.status.value} result.",
        evidence={
            "run_id": str(result.run_id),
            "artifacts": [item.uri for item in result.artifacts],
        },
    )
