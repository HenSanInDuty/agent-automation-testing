"""SQLAlchemy schema; business rules remain in ``domain``."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantRecord:
    tenant_id: Mapped[str] = mapped_column(String(200), index=True)


class UserModel(Base):
    """A person identity; tenancy and authorization grants live in memberships."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    force_password_change: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantMembershipModel(TenantRecord, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_user"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionModel(Base):
    """Opaque tokens are represented only by their SHA-256 digest."""

    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConfigurationModel(TenantRecord, Base):
    """Non-secret configuration, scoped for a future tenant-admin UI."""

    __tablename__ = "configs"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(200))
    value: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


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
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class ProjectExecutionPolicyModel(TenantRecord, Base):
    __tablename__ = "project_execution_policies"
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    allowed_origins: Mapped[list[str]] = mapped_column(JSONB, default=list)
    vision_max_hops: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    vision_max_states: Mapped[int] = mapped_column(Integer, nullable=False, default=50)


class VisualExplorationSessionModel(TenantRecord, Base):
    """Advisory-session metadata; screenshots never persist here."""

    __tablename__ = "visual_exploration_sessions"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    target_url: Mapped[str] = mapped_column(Text)
    intent_hash: Mapped[str] = mapped_column(String(64))
    encrypted_task_intent: Mapped[str] = mapped_column(Text)
    intent_retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    policy_version: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    max_steps: Mapped[int] = mapped_column(Integer)
    max_hops: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_states: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_screenshot_bytes: Mapped[int] = mapped_column(Integer)
    max_session_seconds: Mapped[int] = mapped_column(Integer)
    max_cost_usd: Mapped[str] = mapped_column(String(32))
    max_requests_per_minute: Mapped[int] = mapped_column(Integer)
    safe_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class VisualActionProposalModel(TenantRecord, Base):
    """Immutable, schema-validated candidate actions without raw image content."""

    __tablename__ = "visual_action_proposals"
    __table_args__ = (UniqueConstraint("session_id", "sequence"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("visual_exploration_sessions.id"), index=True
    )
    originating_state_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("visual_exploration_states.id"), nullable=True, index=True
    )
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    action: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    evidence_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class VisualExplorationStateModel(TenantRecord, Base):
    """Safe BFS checkpoint metadata; replay actions and screenshots stay out of the DB."""

    __tablename__ = "visual_exploration_states"
    __table_args__ = (UniqueConstraint("session_id", "id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("visual_exploration_sessions.id"), index=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    hop: Mapped[int] = mapped_column(Integer)
    screenshot_checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class VisualReplayFrameModel(TenantRecord, Base):
    """Private, persistent screenshot metadata for an advisory Vision state."""

    __tablename__ = "visual_replay_frames"
    __table_args__ = (
        UniqueConstraint("session_id", "state_id", name="uq_visual_replay_frame_state"),
        Index(
            "ix_visual_replay_frames_tenant_session_sequence",
            "tenant_id",
            "session_id",
            "sequence",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("visual_exploration_sessions.id"), index=True
    )
    state_id: Mapped[UUID] = mapped_column(ForeignKey("visual_exploration_states.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VisionDebugEvidenceModel(TenantRecord, Base):
    """Encrypted privileged diagnostics; never use this model in normal Vision reads."""

    __tablename__ = "vision_debug_evidence"
    __table_args__ = (
        UniqueConstraint("session_id", "state_id", "attempt_key", name="uq_vision_debug_attempt"),
        Index("ix_vision_debug_evidence_tenant_session", "tenant_id", "session_id"),
        Index("ix_vision_debug_evidence_retention", "retention_until", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("visual_exploration_sessions.id"), index=True
    )
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    state_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    attempt_key: Mapped[str] = mapped_column(String(200), nullable=False)
    diagnostic_code: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    redaction_version: Mapped[str] = mapped_column(String(100), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GenerationRequestModel(TenantRecord, Base):
    __tablename__ = "generation_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    target_url: Mapped[str] = mapped_column(Text)
    redacted_request: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))


class GeneratedTestDraftModel(TenantRecord, Base):
    __tablename__ = "generated_test_drafts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    planning_request_id: Mapped[UUID] = mapped_column(
        ForeignKey("generation_requests.id"), unique=True
    )
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    playwright_test_source: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    stop_conditions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    linked_test_case_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    linked_run_id: Mapped[UUID | None] = mapped_column(nullable=True)


class GeneratedTestDecisionModel(TenantRecord, Base):
    __tablename__ = "generated_test_decisions"
    __table_args__ = (UniqueConstraint("draft_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("generated_test_drafts.id"))
    approved: Mapped[bool] = mapped_column()
    decided_by: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )


class ArtifactModel(TenantRecord, Base):
    __tablename__ = "artifacts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("test_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    uri: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column()
    content_type: Mapped[str | None] = mapped_column(String(200))
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunReportModel(TenantRecord, Base):
    __tablename__ = "run_reports"
    __table_args__ = (UniqueConstraint("tenant_id", "run_id", "report_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    deterministic_status: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalModel(TenantRecord, Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("proposal_id", "proposal_version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(ForeignKey("agent_proposals.id"))
    proposal_version: Mapped[int] = mapped_column()
    approved: Mapped[bool] = mapped_column()
    decided_by: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventModel(TenantRecord, Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[UUID] = mapped_column(index=True)
    correlation_id: Mapped[UUID] = mapped_column(index=True)


class ActivityEventModel(TenantRecord, Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_run_timeline", "tenant_id", "run_id", "occurred_at"),
        Index(
            "ix_activity_events_correlation_timeline",
            "tenant_id",
            "correlation_id",
            "occurred_at",
        ),
        Index(
            "ix_activity_events_vision_session_timeline",
            "tenant_id",
            "visual_exploration_session_id",
            "occurred_at",
        ),
        UniqueConstraint(
            "visual_exploration_session_id", "progress_key", name="uq_activity_vision_progress"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=True
    )
    visual_exploration_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("visual_exploration_sessions.id"), nullable=True
    )
    progress_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(32))
    stage: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32))
    safe_summary: Mapped[str] = mapped_column(Text)
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class OutboxEventModel(TenantRecord, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_unpublished", "published_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(200))
    schema_version: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[UUID] = mapped_column(index=True)
    causation_id: Mapped[UUID | None] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
