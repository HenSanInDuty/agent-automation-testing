"""Provider-neutral domain records that will later be persisted by adapters."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from auto_at.contracts.agent import ProposalKind
from auto_at.contracts.execution import TargetType


class ApprovalStateError(ValueError):
    """Raised when an approval would replace a recorded final decision."""


@dataclass(frozen=True)
class Project:
    id: UUID
    tenant_id: str
    name: str
    default_target: TargetType


@dataclass(frozen=True)
class TestCase:
    id: str
    tenant_id: str
    project_id: UUID
    target_type: TargetType
    revision: str
    specification: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactRecord:
    id: UUID
    tenant_id: str
    run_id: UUID
    kind: str
    uri: str
    checksum: str
    size: int
    content_type: str | None = None
    retention_until: datetime | None = None


@dataclass
class ProposalRecord:
    id: UUID
    tenant_id: str
    run_id: UUID
    correlation_id: UUID
    kind: ProposalKind
    proposal_version: int
    summary: str
    created_at: datetime
    final_approval: "ApprovalRecord | None" = None

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        run_id: UUID,
        correlation_id: UUID,
        kind: ProposalKind,
        proposal_version: int,
        summary: str,
    ) -> "ProposalRecord":
        if proposal_version < 1:
            raise ValueError("proposal_version must be positive")
        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            run_id=run_id,
            correlation_id=correlation_id,
            kind=kind,
            proposal_version=proposal_version,
            summary=summary,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class ApprovalRecord:
    id: UUID
    proposal_id: UUID
    proposal_version: int
    approved: bool
    decided_by: str
    decided_at: datetime

    @classmethod
    def decide(
        cls, proposal: ProposalRecord, *, approved: bool, decided_by: str
    ) -> "ApprovalRecord":
        if proposal.final_approval is not None:
            raise ApprovalStateError("a proposal version already has a final approval")
        decision = cls(
            id=uuid4(),
            proposal_id=proposal.id,
            proposal_version=proposal.proposal_version,
            approved=approved,
            decided_by=decided_by,
            decided_at=datetime.now(UTC),
        )
        proposal.final_approval = decision
        return decision
