"""Private v4 worker transport. Browser input values exist only in request/session RAM."""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from auto_at.contracts.codex_bridge import (
    CodexBoundObservation,
    ElementId,
)
from auto_at.contracts.vision import (
    Fingerprint,
    VisualCheckpoint,
    VisualLocatorDescriptor,
    VisualLocatorEvidence,
    VisualOperation,
    VisualOperationFrame,
)
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class VisualWorkerIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["v4"] = "v4"
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    session_id: UUID
    fencing_token: int = Field(ge=1, le=9_007_199_254_740_991)


class VisualWorkerOpen(VisualWorkerIdentity):
    target_url: str = Field(min_length=1, max_length=2000)
    allowed_origins: tuple[str, ...] = Field(min_length=0, max_length=100)
    deadline: datetime
    max_session_seconds: int = Field(ge=1, le=3600)
    step_timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    max_states: int = Field(ge=1, le=200)
    max_hops: int = Field(ge=1, le=20)
    max_screenshot_bytes: int = Field(ge=1024, le=5_000_000)
    interaction_scope: Literal["all", "buttons", "visual_buttons"] = "all"
    required_capabilities: tuple[Literal[
        "dom-observation-v1", "step-timeout-v1", "button-scope-v1", "anonymous-button-v1",
        "visual-button-scope-v1", "viewport-context-v1", "target-preflight-v1",
        "click-context-v1", "agent-dom-path-v1",
    ], ...] = Field(
        default=(), max_length=9,
    )
    # Agent-loop engine only: relaxes worker guards behind one flag and carries the single
    # source of sensitive-control terms (owned by the control plane).
    agent_mode: bool = False
    blocked_action_terms: tuple[Annotated[str, Field(min_length=1, max_length=40)], ...] = Field(
        default=(), max_length=40,
    )


class VisualWorkerCheckTarget(VisualWorkerIdentity):
    """Read-only validation of an approved target; allocates no operation or snapshot."""

    snapshot_id: UUID
    element_id: ElementId
    checkpoint_id: UUID
    allow_restored_document: bool = False


class VisualWorkerTargetCheck(VisualWorkerCheckTarget):
    matches_current: StrictBool
    context_matches: StrictBool
    same_document: StrictBool


class VisualWorkerObserveDom(VisualWorkerIdentity):
    capability: Literal["dom-observation-v1"] = "dom-observation-v1"
    expected_state_fingerprint: Fingerprint
    snapshot_id: UUID
    max_elements: int = Field(default=100, ge=1, le=100)
    max_bytes: int = Field(default=65_536, ge=1024, le=65_536)
    revalidate_snapshot_id: UUID | None = None
    revalidate_element_ids: tuple[ElementId, ...] = Field(default=(), max_length=10)
    revalidate_context_only: bool = False

    @model_validator(mode="after")
    def revalidation_pair(self):
        if self.revalidate_context_only and (
            not self.revalidate_snapshot_id or self.revalidate_element_ids
        ):
            raise ValueError("context-only revalidation requires a snapshot and no targets")
        if not self.revalidate_context_only and (
            bool(self.revalidate_snapshot_id) != bool(self.revalidate_element_ids)
        ):
            raise ValueError("revalidation requires a snapshot and targets")
        if len(set(self.revalidate_element_ids)) != len(self.revalidate_element_ids):
            raise ValueError("duplicate revalidation target")
        return self


class VisualWorkerDomObservation(VisualWorkerIdentity):
    capability: Literal["dom-observation-v1"] = "dom-observation-v1"
    data: CodexBoundObservation

    @model_validator(mode="after")
    def observation_scope(self):
        observed = self.data.observation
        if any(getattr(self, key) != getattr(observed, key)
               for key in ("tenant_id", "project_id", "session_id", "fencing_token")):
            raise ValueError("DOM observation scope mismatch")
        return self


class VisualExternalOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: str = Field(min_length=1, max_length=500)
    request_kind: Literal["navigation", "popup", "resource", "websocket"]
    observed_at: datetime

    @field_validator("origin")
    @classmethod
    def origin_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or value != f"{parsed.scheme}://{parsed.netloc}"
                or any(char.isspace() or ord(char) < 32 for char in value)):
            raise ValueError("observation must contain only an HTTP origin")
        return value


class VisualWorkerOriginObservations(VisualWorkerIdentity):
    items: tuple[VisualExternalOrigin, ...] = Field(max_length=100)
    truncated: bool


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
    step_deadline: datetime | None = None
    operation_id: UUID
    refresh_observation: bool = False
    purpose: Literal["explore", "restore", "replay", "setup"]
    action: VisualWorkerAction
    expected_state_fingerprint: Fingerprint
    state_id: UUID | None = None
    proposal_id: UUID | None = None
    model_confidence: float = Field(default=0, ge=0, le=1)
    checkpoint_id: UUID | None = None
    checkpoint_state_id: UUID | None = None
    restore_checkpoint_id: UUID | None = None
    history_checkpoint_id: UUID | None = None
    replay_operation_id: UUID | None = None
    expected_locator: VisualLocatorDescriptor | None = None
    dom_snapshot_id: UUID | None = None
    dom_element_id: ElementId | None = None

    @model_validator(mode="after")
    def references(self) -> "VisualWorkerPrepare":
        if self.history_checkpoint_id and (
            self.purpose != "restore" or self.action.kind != "back"
            or self.restore_checkpoint_id or self.checkpoint_id or self.replay_operation_id
        ):
            raise ValueError("history selection requires a saved checkpoint and restore Back")
        if self.refresh_observation and (
            self.purpose != "setup" or self.action.kind != "wait" or not self.checkpoint_id
            or self.proposal_id or self.dom_snapshot_id or self.expected_locator
            or self.restore_checkpoint_id or self.replay_operation_id
        ):
            raise ValueError("observation refresh requires a new read-only setup checkpoint")
        if (self.dom_snapshot_id is None) != (self.dom_element_id is None):
            raise ValueError("DOM prepare requires snapshot and element together")
        if self.dom_snapshot_id and self.action.kind not in {"click", "type"}:
            raise ValueError("DOM binding requires a target action")
        if (self.expected_locator and self.expected_locator.strategy == "dom_path"
                and not self.dom_snapshot_id):
            raise ValueError("ephemeral locator requires its live DOM snapshot")
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
    history_restore_available: bool = False

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
    # Older workers provide no dispatch proof; absence never authorizes recovery.
    dispatch_started: bool | None = None
    failure_stage: Literal["prepare", "before_dispatch"] | None = None

    @model_validator(mode="after")
    def evidence_scope(self) -> "VisualWorkerOperationResult":
        op = self.operation
        if self.failure_stage is not None and (
            self.dispatch_started is not False or op.status != "rejected"
        ):
            raise ValueError("pre-dispatch failure requires a rejected, undispatched operation")
        if self.dispatch_started is False and op.status in {"completed", "executing", "unknown"}:
            raise ValueError("operation status conflicts with dispatch proof")
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
