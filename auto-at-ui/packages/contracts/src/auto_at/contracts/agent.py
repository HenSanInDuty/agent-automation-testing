from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ProposalKind(StrEnum):
    TRIAGE = "triage"
    TEST_GENERATION = "test_generation"
    HEALING = "healing"


class AgentProposal(BaseModel):
    """A reviewable, auditable suggestion from an agent; never an execution verdict."""

    id: UUID = Field(default_factory=uuid4)
    kind: ProposalKind
    correlation_id: UUID
    summary: str = Field(min_length=1, max_length=4000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    proposed_change: dict[str, Any] | None = None


class ApprovalDecision(BaseModel):
    proposal_id: UUID
    approved: bool
    decided_by: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)
