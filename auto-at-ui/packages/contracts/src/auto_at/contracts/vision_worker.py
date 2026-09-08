"""Private v4 worker transport. Browser input values exist only in request/session RAM."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from auto_at.contracts.vision import (
    Fingerprint,
    VisualCheckpoint,
    VisualLocatorDescriptor,
    VisualLocatorEvidence,
    VisualOperation,
    VisualOperationFrame,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class VisualWorkerIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["v4"] = "v4"
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    session_id: UUID
    fencing_token: int = Field(ge=1, le=9_007_199_254_740_991)


class VisualWorkerOpen(VisualWorkerIdentity):
    target_url: str = Field(min_length=1, max_length=2000)
    allowed_origins: tuple[str, ...] = Field(min_length=1, max_length=100)
    deadline: datetime
    max_session_seconds: int = Field(ge=1, le=3600)
    max_states: int = Field(ge=1, le=200)
    max_hops: int = Field(ge=1, le=10)
    max_screenshot_bytes: int = Field(ge=1024, le=5_000_000)


class VisualWorkerAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["click", "type", "scroll", "wait", "navigate", "back", "close_popup"]
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    delta_y: int | None = Field(default=None, ge=-2000, le=2000)
    duration_ms: int | None = Field(default=None, ge=100, le=10_000)

    @model_validator(mode="after")
    def action_fields(self) -> "VisualWorkerAction":
        required = {
            "click": {"x", "y"},
            "type": {"x", "y", "text"},
            "scroll": {"delta_y"},
            "wait": {"duration_ms"},
        }.get(self.kind, set())
        present = {
            key
            for key in ("x", "y", "text", "delta_y", "duration_ms")
            if getattr(self, key) is not None
        }
        if present != required:
            raise ValueError("action fields do not match kind")
        return self


class VisualWorkerPrepare(VisualWorkerIdentity):
    operation_id: UUID
    purpose: Literal["explore", "restore", "replay", "setup"]
    action: VisualWorkerAction
    expected_state_fingerprint: Fingerprint
    state_id: UUID | None = None
    proposal_id: UUID | None = None
    model_confidence: float = Field(default=0, ge=0, le=1)
    checkpoint_id: UUID | None = None
    checkpoint_state_id: UUID | None = None
    restore_checkpoint_id: UUID | None = None
    replay_operation_id: UUID | None = None
    expected_locator: VisualLocatorDescriptor | None = None

    @model_validator(mode="after")
    def references(self) -> "VisualWorkerPrepare":
        if self.action.kind in {"click", "type"} and not (self.state_id and self.proposal_id):
            raise ValueError("target action requires state and proposal")
        if (self.checkpoint_id is None) != (self.checkpoint_state_id is None):
            raise ValueError("checkpoint requires state")
        if self.purpose == "replay" and not self.replay_operation_id:
            raise ValueError("replay requires a previously completed operation")
        return self


class VisualWorkerExecute(VisualWorkerIdentity):
    operation_id: UUID
    prepared_handle: UUID
    before_frame_id: UUID
    before_checksum: Fingerprint
    before_persisted: Literal[True]


class VisualWorkerAck(VisualWorkerIdentity):
    operation_id: UUID
    # Empty is valid only if capture failed and the operation has no frames.
    persisted_frame_ids: tuple[UUID, ...] = Field(max_length=2)


class VisualWorkerOperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: VisualOperation
    frames: tuple[VisualOperationFrame, ...] = Field(max_length=2)
    locator: VisualLocatorEvidence | None
    prepared_handle: UUID
    state_fingerprint: Fingerprint | None
    checkpoint: VisualCheckpoint | None
    semantic_change: Literal["changed", "unchanged", "unavailable"]
    duration_ms: int = Field(ge=0, le=3_600_000)
    acknowledged: bool
    replayable: bool

    @model_validator(mode="after")
    def evidence_scope(self) -> "VisualWorkerOperationResult":
        op = self.operation
        if len({frame.role for frame in self.frames}) != len(self.frames):
            raise ValueError("duplicate frame role")
        for item in (*self.frames, *((self.locator,) if self.locator else ())):
            if (item.tenant_id, item.project_id, item.session_id, item.operation_id) != (
                op.tenant_id,
                op.project_id,
                op.session_id,
                op.id,
            ):
                raise ValueError("evidence scope mismatch")
        for frame in self.frames:
            if frame.id != getattr(op, f"actual_{frame.role}_frame_id"):
                raise ValueError("frame reference mismatch")
        if self.locator and (
            self.locator.id != op.locator_id
            or self.locator.originating_frame_id != op.actual_before_frame_id
        ):
            raise ValueError("locator reference mismatch")
        return self
