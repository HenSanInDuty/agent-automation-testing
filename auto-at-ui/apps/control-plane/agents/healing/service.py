"""Healing proposals are ranked data only; they never execute a change."""

from auto_at.contracts.agent import HealingProposal


def rank_healing_proposals(candidates: list[HealingProposal]) -> list[HealingProposal]:
    """Return bounded review candidates ordered by confidence without side effects."""
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)[:5]
