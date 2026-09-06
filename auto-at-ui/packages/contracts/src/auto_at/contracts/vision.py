"""Versioned, advisory-only contracts for bounded visual exploration."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class VisualExplorationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


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
