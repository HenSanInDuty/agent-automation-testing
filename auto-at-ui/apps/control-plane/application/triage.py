"""Persistence boundary for advisory triage outcomes."""

from uuid import UUID

from agents.shared.runtime import AgentRuntimeConfig
from auto_at.contracts.agent import AgentProposal
from domain.entities import ProposalRecord
from domain.ports import ProposalRepository


class PersistTriageProposal:
    """Persist a reviewable triage record; it never changes a run's verdict."""

    def __init__(self, proposals: ProposalRepository) -> None:
        self._proposals = proposals

    def execute(
        self,
        *,
        tenant_id: str,
        run_id: UUID,
        proposal: AgentProposal,
        runtime: AgentRuntimeConfig,
    ) -> ProposalRecord:
        record = ProposalRecord.create(
            tenant_id=tenant_id,
            run_id=run_id,
            correlation_id=proposal.correlation_id,
            kind=proposal.kind,
            proposal_version=1,
            summary=proposal.summary,
            payload={
                "evidence": proposal.evidence,
                "proposed_change": proposal.proposed_change,
                "provenance": {
                    "provider": runtime.provider,
                    "model": runtime.model,
                    "prompt_version": "triage-v1",
                },
            },
        )
        self._proposals.add(record)
        return record
