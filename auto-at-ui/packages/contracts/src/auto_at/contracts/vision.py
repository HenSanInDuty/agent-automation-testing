"""Versioned, advisory-only contracts for bounded visual exploration."""

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VisualExplorationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


class VisualTrajectoryEdgeStatus(StrEnum):
    PROPOSED = "proposed"
    ATTEMPTING = "attempting"
    OBSERVED = "observed"
    NO_MEANINGFUL_CHANGE = "no_meaningful_change"
    REJECTED = "rejected"
    FAILED = "failed"
    TERMINAL = "terminal"


class VisualTrajectoryOutcomeCode(StrEnum):
    MODEL_STOP = "model_stop"
    HOP_LIMIT = "hop_limit"
    STATE_LIMIT = "state_limit"
    SESSION_TIMEOUT = "session_timeout"
    POLICY_BLOCK = "policy_block"
    NAVIGATION_FAILED = "navigation_failed"
    CAPTURE_FAILED = "capture_failed"
    CANDIDATE_REJECTED = "candidate_rejected"
    DRAFT_HANDOFF_UNAVAILABLE = "draft_handoff_unavailable"


class VisualUrlChangeClassification(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNAVAILABLE = "unavailable"


class VisualTrajectoryActionSummary(BaseModel):
    """Redacted action metadata that can be shown without typed values or model rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["click", "type", "scroll", "wait", "stop"]
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    delta_y: int | None = Field(default=None, ge=-2_000, le=2_000)
    duration_ms: int | None = Field(default=None, ge=100, le=10_000)


class VisualTrajectoryEdge(BaseModel):
    """Immutable advisory edge joining one proposed action to its observed outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    id: UUID
    tenant_id: str = Field(min_length=1, max_length=200)
    session_id: UUID
    parent_state_id: UUID
    proposal_id: UUID
    attempt: int = Field(ge=1, le=100)
    action: VisualTrajectoryActionSummary
    confidence: float = Field(ge=0, le=1)
    status: VisualTrajectoryEdgeStatus
    outcome_code: VisualTrajectoryOutcomeCode | None = None
    child_state_id: UUID | None = None
    observed_at: datetime | None = None
    duration_ms: int = Field(ge=0, le=3_600_000)
    url_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    url_change: VisualUrlChangeClassification = VisualUrlChangeClassification.UNAVAILABLE
    child_screenshot_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class VisualEvidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_type: Literal["image/png", "image/jpeg"]
    byte_count: int = Field(ge=1, le=5_000_000)


class VisualReplayFrame(BaseModel):
    """Metadata for one retained replay frame; locations and bytes stay private."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    id: UUID
    session_id: UUID
    state_id: UUID
    sequence: int = Field(ge=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_count: int = Field(ge=1, le=5_000_000)
    content_type: Literal["image/png", "image/jpeg"]
    captured_at: datetime


class VisualActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0, le=1)
    expected_outcome: str = Field(min_length=1, max_length=1_000)


class ClickAction(VisualActionBase):
    kind: Literal["click"] = "click"
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class TypeAction(VisualActionBase):
    kind: Literal["type"] = "type"
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    text: str = Field(min_length=1, max_length=1_000)


class ScrollAction(VisualActionBase):
    kind: Literal["scroll"] = "scroll"
    delta_y: int = Field(ge=-2_000, le=2_000)


class WaitAction(VisualActionBase):
    kind: Literal["wait"] = "wait"
    duration_ms: int = Field(ge=100, le=10_000)


class StopAction(VisualActionBase):
    kind: Literal["stop"] = "stop"


VisualAction = Annotated[
    ClickAction | TypeAction | ScrollAction | WaitAction | StopAction,
    Field(discriminator="kind"),
]


class VisualExplorationRequest(BaseModel):
    """Worker input, separate from TestExecutionRequest and never a verdict."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v1"] = "v1"
    id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    correlation_id: UUID
    target_url: str = Field(min_length=1, max_length=2_000)
    task_intent: str = Field(min_length=1, max_length=4_000)
    allowed_origins: list[str] = Field(min_length=1, max_length=100)
    max_steps: int = Field(ge=1, le=10)
    max_screenshot_bytes: int = Field(ge=1_024, le=5_000_000)
    max_session_seconds: int = Field(ge=1, le=3_600)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)


class VisualStateNode(BaseModel):
    """Safe state-graph provenance; never contains screenshot bytes or URLs."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    parent_id: UUID | None = None
    hop: int = Field(ge=0, le=10)
    screenshot_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")


class VisualActionCandidateBatch(BaseModel):
    """A bounded BFS expansion proposed for one state node."""

    model_config = ConfigDict(extra="forbid")

    state_id: UUID
    candidates: list[VisualAction] = Field(min_length=1, max_length=20)


class VisualExplorationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["v1"] = "v1"
    session_id: UUID
    correlation_id: UUID
    state: VisualExplorationState
    actions: list[VisualAction] = Field(default_factory=list, max_length=10)
    evidence: list[VisualEvidenceMetadata] = Field(default_factory=list, max_length=20)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)
    safe_failure_reason: str | None = Field(default=None, max_length=1_000)


# These contracts describe observations, never executable source or test verdicts.
Fingerprint = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")]
_SENSITIVE_LOCATOR = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_ -]?key|authorization|cookie)\b"
    r"|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{7,}\b|https?://|\[redacted\])"
)
_CSS_LOCATOR = re.compile(
    r'(?:[a-z][a-z0-9-]*)?\[(?:id|data-testid|name|aria-label|title)="[^"\\\r\n]+"\]'
)


def validate_locator_value(value: str) -> str:
    """Reject sensitive identities instead of turning them into verified placeholders."""
    if value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("locator value contains whitespace or control characters")
    if _SENSITIVE_LOCATOR.search(value):
        raise ValueError("locator identity requires redaction and cannot be persisted")
    return value


class VisualLocatorScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["iframe", "shadow"]
    selector: str = Field(min_length=1, max_length=240)

    @field_validator("selector")
    @classmethod
    def stable_scope(cls, value: str) -> str:
        validate_locator_value(value)
        if not _CSS_LOCATOR.fullmatch(value):
            raise ValueError("scope requires a single stable CSS attribute selector")
        return value


class VisualLocatorDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    strategy: Literal["role", "label", "test_id", "css"]
    value: str = Field(min_length=1, max_length=240)
    role: str | None = Field(default=None, pattern=r"^[a-z]{3,32}$")
    exact: Literal[True] = True
    scope: tuple[VisualLocatorScope, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def safe_descriptor(self) -> "VisualLocatorDescriptor":
        validate_locator_value(self.value)
        if (self.strategy == "role") != (self.role is not None):
            raise ValueError("role is required only for the role strategy")
        if self.strategy == "css" and not _CSS_LOCATOR.fullmatch(self.value):
            raise ValueError("CSS requires a single stable attribute selector")
        return self


class VisualBoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def in_viewport(self) -> "VisualBoundingBox":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("bounding box must fit the viewport")
        return self


class VisualTraceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    id: UUID
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    session_id: UUID


class VisualLocatorEvidence(VisualTraceIdentity):
    operation_id: UUID
    state_id: UUID
    proposal_id: UUID
    originating_frame_id: UUID
    descriptor: VisualLocatorDescriptor | None = None
    bounding_box: VisualBoundingBox | None = None
    matched_count: int = Field(ge=0, le=100_000)
    target_match: bool = False
    actionable: bool = False
    model_confidence: float = Field(ge=0, le=1)
    verified_at: datetime | None = None
    status: Literal["verified", "ambiguous", "not_found", "stale", "unsupported", "redacted"]
    reason_code: SafeCode | None = None

    @model_validator(mode="after")
    def verified_requires_evidence(self) -> "VisualLocatorEvidence":
        if self.status == "verified":
            if not (
                self.descriptor
                and self.bounding_box
                and self.matched_count == 1
                and self.target_match
                and self.actionable
                and self.verified_at
            ):
                raise ValueError("verified locator requires unique grounded actionable evidence")
            if self.reason_code is not None:
                raise ValueError("verified locator cannot carry a failure reason")
        elif self.reason_code is None or self.verified_at is not None:
            raise ValueError("unresolved locator requires a reason and no verification timestamp")
        if self.status == "redacted" and self.descriptor is not None:
            raise ValueError("redacted locator must omit the descriptor")
        return self


class VisualOperation(VisualTraceIdentity):
    sequence: int = Field(ge=1, le=100_000)
    attempt: int = Field(default=1, ge=1, le=100)
    parent_operation_id: UUID | None = None
    checkpoint_id: UUID | None = None
    edge_id: UUID | None = None
    state_id: UUID | None = None
    proposal_id: UUID | None = None
    purpose: Literal["explore", "restore", "replay", "setup"]
    action_kind: Literal["click", "type", "scroll", "wait", "navigate", "back", "close_popup"]
    locator_id: UUID | None = None
    expected_parent_fingerprint: Fingerprint | None = None
    started_at: datetime
    ended_at: datetime | None = None
    status: Literal["prepared", "executing", "completed", "failed", "unknown", "rejected"]
    outcome_code: SafeCode | None = None
    actual_before_frame_id: UUID | None = None
    actual_after_frame_id: UUID | None = None
    before_unavailable_reason: SafeCode | None = None
    after_unavailable_reason: SafeCode | None = None
    before_page_id: UUID | None = None
    after_page_id: UUID | None = None
    url_change: Literal["unchanged", "changed", "unavailable"] = "unavailable"
    visual_change: Literal["unchanged", "changed", "unavailable"] = "unavailable"

    @model_validator(mode="after")
    def lifecycle_shape(self) -> "VisualOperation":
        final = self.status in {"completed", "failed", "unknown", "rejected"}
        if final != (self.ended_at is not None):
            raise ValueError("only finalized operations have ended_at")
        if self.ended_at and self.ended_at < self.started_at:
            raise ValueError("operation cannot end before it starts")
        if self.status in {"executing", "completed"} and not self.actual_before_frame_id:
            raise ValueError("execution requires an actual before frame")
        if final:
            if not self.outcome_code:
                raise ValueError("final operation requires a safe outcome code")
            for role in ("before", "after"):
                if not (
                    getattr(self, f"actual_{role}_frame_id")
                    or getattr(self, f"{role}_unavailable_reason")
                ):
                    raise ValueError("final operation requires frame or unavailable reason")
        for role in ("before", "after"):
            if getattr(self, f"actual_{role}_frame_id") and getattr(
                self, f"{role}_unavailable_reason"
            ):
                raise ValueError("frame and unavailable reason are mutually exclusive")
        if self.parent_operation_id == self.id:
            raise ValueError("operation cannot parent itself")
        return self


class VisualOperationFrame(VisualTraceIdentity):
    operation_id: UUID
    role: Literal["before", "after"]
    checksum: Fingerprint
    byte_count: int = Field(ge=1, le=5_000_000)
    content_type: Literal["image/png", "image/jpeg"]
    captured_at: datetime
    deleted_at: datetime | None = None


class VisualCheckpoint(BaseModel):
    """Safe invariants only. Browser heap, form values and storage remain in worker RAM."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    state_id: UUID
    ancestor_operation_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    url_fingerprint: Fingerprint
    semantic_fingerprint: Fingerprint
    scroll_x: int = Field(ge=0, le=10_000_000)
    scroll_y: int = Field(ge=0, le=10_000_000)
    form_presence_fingerprint: Fingerprint | None = None


class VisualHandoffStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    locator_id: UUID | None = None
    input_reference: UUID | None = None
    observation_codes: tuple[SafeCode, ...] = Field(default=(), max_length=20)


class VisualHandoffBranch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    steps: tuple[VisualHandoffStep, ...] = Field(min_length=1, max_length=100)
    status: Literal["ready", "blocked"]
    reason_code: SafeCode | None = None

    @model_validator(mode="after")
    def input_binding(self) -> "VisualHandoffBranch":
        if len({step.operation_id for step in self.steps}) != len(self.steps):
            raise ValueError("branch contains duplicate operations")
        if (self.status == "blocked") != (self.reason_code is not None):
            raise ValueError("blocked branch requires a reason")
        if any(step.input_reference for step in self.steps):
            if self.status != "blocked" or self.reason_code != "input_binding_required":
                raise ValueError("input_binding_required")
        return self


class VisualLocatorHandoff(VisualTraceIdentity):
    version: int = Field(ge=1, le=100)
    branches: tuple[VisualHandoffBranch, ...] = Field(default=(), max_length=50)
    unresolved_count: int = Field(ge=0, le=100_000)
    created_at: datetime
    content_hash: Fingerprint

    def compute_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def validate_hash(self) -> "VisualLocatorHandoff":
        if len({branch.id for branch in self.branches}) != len(self.branches):
            raise ValueError("handoff branch IDs must be unique")
        if self.content_hash != self.compute_hash():
            raise ValueError("handoff content_hash mismatch")
        return self


class VisualWorkerCommand(BaseModel):
    """v4 control message, independent of the deterministic execution v1 envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["v4"] = "v4"
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    session_id: UUID
    fencing_token: int = Field(ge=1)
    operation_id: UUID
    command: Literal["prepare", "execute", "observe", "restore", "close"]
    deadline: datetime
