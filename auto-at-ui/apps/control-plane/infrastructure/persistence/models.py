"""SQLAlchemy schema; business rules remain in ``domain``."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantRecord:
    tenant_id: Mapped[str] = mapped_column(String(200), index=True)


class ProjectModel(TenantRecord, Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    default_target: Mapped[str] = mapped_column(String(32))


class TestCaseModel(TenantRecord, Base):
    __tablename__ = "test_cases"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    target_type: Mapped[str] = mapped_column(String(32))
    revision: Mapped[str] = mapped_column(String(128))
    specification: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


class TestRunModel(TenantRecord, Base):
    __tablename__ = "test_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id"))
    revision: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True)
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    request: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ArtifactModel(TenantRecord, Base):
    __tablename__ = "artifacts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("test_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    uri: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column()
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentProposalModel(TenantRecord, Base):
    __tablename__ = "agent_proposals"
    __table_args__ = (UniqueConstraint("id", "proposal_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("test_runs.id"))
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(50))
    proposal_version: Mapped[int] = mapped_column(default=1)
    summary: Mapped[str] = mapped_column(Text)
    proposal: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


class ApprovalModel(TenantRecord, Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("proposal_id", "proposal_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("agent_proposals.id"))
    proposal_version: Mapped[int] = mapped_column()
    approved: Mapped[bool]
    decided_by: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(Text)


class AuditEventModel(TenantRecord, Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[UUID] = mapped_column(index=True)
    correlation_id: Mapped[UUID] = mapped_column(index=True)


class OutboxEventModel(TenantRecord, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_unpublished", "published_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(200))
    schema_version: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    causation_id: Mapped[UUID | None]
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
