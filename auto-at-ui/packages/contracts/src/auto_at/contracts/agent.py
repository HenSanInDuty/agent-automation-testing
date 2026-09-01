from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ProposalKind(StrEnum):
    TRIAGE = "triage"
    TEST_GENERATION = "test_generation"
    HEALING = "healing"
    VISION = "vision"


class RunReportStatus(StrEnum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"


class TriageCategory(StrEnum):
    PRODUCT = "product"
    TEST = "test"
    ENVIRONMENT = "environment"
    FLAKY = "flaky"
    UNKNOWN = "unknown"


class EvidenceReference(BaseModel):
    """Reference only; binary evidence stays in artifact storage."""

    kind: str = Field(min_length=1, max_length=100)
    uri: str = Field(min_length=1, max_length=2_000)
    content_type: str | None = Field(default=None, max_length=200)


class EvidenceBundle(BaseModel):
    """Bounded, redacted context permitted to cross into an agent prompt."""

    contract_version: Literal["v1"] = "v1"
    run_id: UUID
    correlation_id: UUID
    deterministic_status: str = Field(min_length=1, max_length=32)
    summary: str = Field(min_length=1, max_length=4_000)
    runner_metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[EvidenceReference] = Field(default_factory=list, max_length=100)
    redaction_policy_version: str = Field(min_length=1, max_length=100)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RedactedTextExcerpt(BaseModel):
    """A bounded, verified textual artifact excerpt permitted in a report prompt."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=100)
    uri: str = Field(min_length=1, max_length=2_000)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_type: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=16_384)


class RunReportEvidenceBundle(EvidenceBundle):
    """Report-specific evidence with bounded redacted text from verified artifacts only."""

    excerpts: list[RedactedTextExcerpt] = Field(default_factory=list, max_length=4)


class TestIntent(BaseModel):
    source_reference: str = Field(min_length=1, max_length=2_000)
    goal: str = Field(min_length=1, max_length=4_000)
    confidence: float = Field(ge=0, le=1)


class TaskSpecification(BaseModel):
    intent: TestIntent
    constraints: list[str] = Field(default_factory=list, max_length=50)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)


class TriageResult(BaseModel):
    category: TriageCategory
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4_000)
    evidence_references: list[str] = Field(default_factory=list, max_length=100)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)


class ProposalProvenance(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=100)
    redaction_policy_version: str = Field(min_length=1, max_length=100)
    evidence_input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    visual_contract_version: str | None = Field(default=None, min_length=1, max_length=100)
    visual_prompt_version: str | None = Field(default=None, min_length=1, max_length=100)


class RunReportObservation(BaseModel):
    """One fact grounded in the bounded, redacted report evidence."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2_000)
    evidence_references: list[str] = Field(default_factory=list, max_length=20)


class RunReportFailure(BaseModel):
    """Safe failure detail, when the permitted evidence makes it available."""

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=1_000)
    message: str = Field(min_length=1, max_length=4_000)
    evidence_references: list[str] = Field(default_factory=list, max_length=20)


class RunReport(BaseModel):
    """Immutable informational account of one deterministic execution result."""

    model_config = ConfigDict(extra="forbid")

    deterministic_status: Literal["passed", "failed", "errored", "skipped"]
    headline: str = Field(min_length=1, max_length=500)
    what_ran: str = Field(min_length=1, max_length=4_000)
    observations: list[RunReportObservation] = Field(default_factory=list, max_length=50)
    failure: RunReportFailure | None = None
    unverified_or_skipped: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=50)


class HealingProposal(BaseModel):
    """Ranked change candidate; it has no authority to apply itself."""

    id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
    summary: str = Field(min_length=1, max_length=4_000)
    confidence: float = Field(ge=0, le=1)
    evidence_references: list[str] = Field(default_factory=list, max_length=100)
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)
    provenance: ProposalProvenance


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
