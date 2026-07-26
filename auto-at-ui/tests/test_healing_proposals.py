from uuid import uuid4

from agents.healing.service import rank_healing_proposals
from auto_at.contracts.agent import HealingProposal, ProposalProvenance


def candidate(confidence: float) -> HealingProposal:
    return HealingProposal(
        correlation_id=uuid4(),
        summary="Locator candidate.",
        confidence=confidence,
        provenance=ProposalProvenance(
            provider="openrouter",
            model="model",
            prompt_version="healing-v1",
            redaction_policy_version="v1",
            evidence_input_hash="a" * 64,
        ),
    )


def test_healing_candidates_are_ranked_and_bounded_without_execution() -> None:
    ranked = rank_healing_proposals([candidate(index / 10) for index in range(7)])
    assert len(ranked) == 5
    assert [item.confidence for item in ranked] == [0.6, 0.5, 0.4, 0.3, 0.2]
