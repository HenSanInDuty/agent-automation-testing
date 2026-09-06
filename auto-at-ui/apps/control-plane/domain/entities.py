"""Provider-neutral domain records that will later be persisted by adapters."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from auto_at.contracts.agent import ProposalKind, RunReport, RunReportStatus
from auto_at.contracts.execution import RunStatus, TargetType


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
    name: str = ""


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


@dataclass(frozen=True)
class VisualReplayFrameRecord:
    """Private Vision replay evidence, separate from deterministic run artifacts."""

    id: UUID
    tenant_id: str
    session_id: UUID
    state_id: UUID
    sequence: int
    storage_key: str
    checksum: str
    size: int
    content_type: str
    captured_at: datetime
    deleted_at: datetime | None = None


@dataclass(frozen=True)
class RunReportRecord:
    """Tenant-scoped, immutable advisory report for one run/version."""

    id: UUID
    tenant_id: str
    run_id: UUID
    correlation_id: UUID
    report_version: int
    schema_version: str
    prompt_version: str
    deterministic_status: RunStatus
    status: RunReportStatus
    payload: RunReport | None
    provenance: dict[str, object]
    input_hash: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        run_id: UUID,
        correlation_id: UUID,
        deterministic_status: RunStatus,
        status: RunReportStatus,
        report_version: int = 1,
        schema_version: str = "v1",
        prompt_version: str = "run-report-v1",
        payload: RunReport | None = None,
        provenance: dict[str, object] | None = None,
        input_hash: str,
    ) -> "RunReportRecord":
        if report_version < 1:
            raise ValueError("report_version must be positive")
        if status is RunReportStatus.COMPLETED and payload is None:
            raise ValueError("completed report requires a payload")
        if status is RunReportStatus.UNAVAILABLE and payload is not None:
            raise ValueError("unavailable report must not persist a payload")
        if len(input_hash) != 64:
            raise ValueError("input_hash must be a SHA-256 digest")
        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            run_id=run_id,
            correlation_id=correlation_id,
            report_version=report_version,
            schema_version=schema_version,
            prompt_version=prompt_version,
            deterministic_status=deterministic_status,
            status=status,
            payload=payload,
            provenance=provenance or {},
            input_hash=input_hash,
            created_at=datetime.now(UTC),
        )


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
    payload: dict[str, object] = field(default_factory=dict)
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
        payload: dict[str, object] | None = None,
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
            payload=payload or {},
        )


@dataclass(frozen=True)
class ApprovalRecord:
    id: UUID
    tenant_id: str
    proposal_id: UUID
    proposal_version: int
    approved: bool
    decided_by: str
    decided_at: datetime
    reason: str | None = None

    @classmethod
    def decide(
        cls, proposal: ProposalRecord, *, approved: bool, decided_by: str, reason: str | None = None
    ) -> "ApprovalRecord":
        if proposal.final_approval is not None:
            raise ApprovalStateError("a proposal version already has a final approval")
        decision = cls(
            id=uuid4(),
            tenant_id=proposal.tenant_id,
            proposal_id=proposal.id,
            proposal_version=proposal.proposal_version,
            approved=approved,
            decided_by=decided_by,
            decided_at=datetime.now(UTC),
            reason=reason,
        )
        proposal.final_approval = decision
        return decision
