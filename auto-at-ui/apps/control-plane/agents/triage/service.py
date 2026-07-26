from auto_at.contracts.agent import AgentProposal, ProposalKind, TriageResult
from auto_at.contracts.execution import TestExecutionResult
from pydantic import ValidationError

from agents.shared.evidence import build_evidence_bundle
from agents.shared.runtime import EvidencePolicy


def propose_failure_triage(
    result: TestExecutionResult, policy: EvidencePolicy | None = None
) -> AgentProposal:
    """Create an advisory record; it cannot alter the deterministic result."""
    evidence = build_evidence_bundle(result, policy or EvidencePolicy())
    return AgentProposal(
        kind=ProposalKind.TRIAGE,
        correlation_id=result.correlation_id,
        summary=f"Triage requested for deterministic {result.status.value} result.",
        evidence=evidence.model_dump(mode="json"),
    )


def validate_triage_output(payload: str) -> TriageResult:
    """Accept only the versioned, typed output contract from a model gateway."""
    try:
        return TriageResult.model_validate_json(payload)
    except ValidationError as error:
        raise ValueError("model returned an invalid triage schema") from error
