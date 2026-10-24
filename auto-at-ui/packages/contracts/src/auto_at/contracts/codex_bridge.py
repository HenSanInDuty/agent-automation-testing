"""Closed v1 contracts for the local proposal bridge; never execution authority."""

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from auto_at.contracts.vision import (
    VisualBoundingBox,
    VisualLocatorDescriptor,
    validate_locator_value,
)
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ElementId = Annotated[str, Field(pattern=r"^e_[a-f0-9]{32}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")]
Stage = Literal["dom", "image"]
JobStatus = Literal["queued", "claimed", "running", "completed", "failed", "cancelled", "expired"]
FailureCode = Literal[
    "bridge_offline", "bridge_cli_unsupported", "bridge_login_required",
    "bridge_model_unavailable", "bridge_stale_result", "bridge_malformed_output",
    "bridge_cancelled", "bridge_deadline_exceeded", "bridge_policy_revoked",
    "bridge_interrupted", "bridge_io_error", "bridge_output_limit", "bridge_queue_full",
    "bridge_tool_rejected", "bridge_provider_unavailable",
    "bridge_cleanup_pending",
]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def canonical_bytes(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def content_hash(value: BaseModel) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class CodexInputPolicy(ClosedModel):
    input_mode: Literal["dom_first"] = "dom_first"
    dom_transfer_accepted: bool = False
    dom_transfer_provider: Literal["codex_cli"] | None = None
    max_dom_elements: int = Field(default=100, ge=1, le=100)
    max_dom_bytes: int = Field(default=65_536, ge=1024, le=65_536)

    @model_validator(mode="after")
    def consent(self):
        if self.dom_transfer_accepted != (self.dom_transfer_provider == "codex_cli"):
            raise ValueError("DOM consent must be explicitly bound to codex_cli")
        return self


class CodexConsentSnapshot(CodexInputPolicy):
    raw_screenshot_transfer_accepted: bool = False
    raw_screenshot_transfer_provider: Literal["codex_cli"] | None = None

    @model_validator(mode="after")
    def image_consent(self):
        if self.raw_screenshot_transfer_accepted != (
            self.raw_screenshot_transfer_provider == "codex_cli"
        ):
            raise ValueError("image consent must be explicitly bound to codex_cli")
        return self


class CodexScope(ClosedModel):
    tenant_id: SafeIdentifier
    project_id: UUID
    session_id: UUID
    fencing_token: int = Field(ge=1, le=9_007_199_254_740_991)


class CodexViewport(ClosedModel):
    width: int = Field(ge=1, le=16_384)
    height: int = Field(ge=1, le=16_384)


class CodexDomElement(ClosedModel):
    element_id: ElementId
    role: str = Field(pattern=r"^[a-z]{1,32}$")
    name: str = Field(max_length=120)
    input_type: Literal[
        "text", "search", "email", "tel", "url", "number", "checkbox", "radio",
        "button", "submit", "reset", "range", "date", "time", "other",
    ] | None = None
    enabled: bool
    editable: bool

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        if value:
            validate_locator_value(value)
        return value


class CodexDomObservation(CodexScope):
    schema_version: Literal["v1"] = "v1"
    observation_id: UUID
    snapshot_id: UUID
    state_fingerprint: Digest
    captured_at: AwareDatetime
    viewport: CodexViewport
    elements: tuple[CodexDomElement, ...] = Field(max_length=100)
    truncated: bool = False
    scrollable: bool = False
    skipped_count: int = Field(default=0, ge=0, le=5000)
    unsupported: tuple[Literal["iframe", "closed_shadow", "canvas", "unbound_target"], ...] = (
        Field(default=(), max_length=4)
    )

    @model_validator(mode="after")
    def bounded(self):
        if len({e.element_id for e in self.elements}) != len(self.elements):
            raise ValueError("duplicate element ID")
        if len(canonical_bytes(self)) > 65_536:
            raise ValueError("DOM observation exceeds byte limit")
        return self


class CodexElementBinding(ClosedModel):
    element_id: ElementId
    descriptor: VisualLocatorDescriptor
    bounds: VisualBoundingBox


class CodexBoundObservation(ClosedModel):
    """Worker-only projection. Only observation is eligible for model transfer."""

    observation: CodexDomObservation
    bindings: tuple[CodexElementBinding, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def binding_ids(self):
        ids = [item.element_id for item in self.bindings]
        if len(set(ids)) != len(ids) or set(ids) != {
            item.element_id for item in self.observation.elements
        }:
            raise ValueError("bindings must match observation elements exactly")
        return self


class CodexProposalBinding(ClosedModel):
    observation_id: UUID
    snapshot_id: UUID
    element_id: ElementId
    state_fingerprint: Digest
    expected_descriptor: VisualLocatorDescriptor


class CodexInputHashes(ClosedModel):
    dom_sha256: Digest
    dom_bytes: int = Field(ge=1, le=65_536)
    schema_sha256: Digest
    schema_bytes: int = Field(ge=1, le=65_536)
    screenshot_sha256: Digest | None = None
    screenshot_bytes: int | None = Field(default=None, ge=1, le=5_000_000)


class CodexTaskContext(ClosedModel):
    task_intent: str = Field(min_length=1, max_length=4000)
    observed_actions: tuple[Annotated[str, Field(max_length=120)], ...] = Field(
        default=(), max_length=10,
    )

    @model_validator(mode="after")
    def byte_limit(self):
        if len(canonical_bytes(self)) > 8192:
            raise ValueError("task context exceeds byte limit")
        return self


class CodexBridgeRequest(CodexScope):
    schema_version: Literal["v1"] = "v1"
    job_id: UUID
    bridge_id: UUID
    correlation_id: UUID
    request_sequence: int = Field(ge=1, le=10)
    observation_id: UUID
    snapshot_id: UUID
    state_fingerprint: Digest
    provider: Literal["codex_cli"] = "codex_cli"
    model: Literal["gpt-6-luna"] = "gpt-6-luna"
    prompt_version: str = Field(pattern=r"^codex-dom-v[1-9][0-9]*$")
    stage: Stage
    created_at: AwareDatetime
    deadline: AwareDatetime
    consent: CodexConsentSnapshot
    consent_hash: Digest
    inputs: CodexInputHashes
    candidate_limit: int = Field(ge=1, le=10)
    max_output_bytes: int = Field(default=32_768, ge=1024, le=32_768)
    context: CodexTaskContext | None = None
    dom_element_count: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def valid_job(self):
        if (self.prompt_version in {
            "codex-dom-v2", "codex-dom-v3", "codex-dom-v4", "codex-dom-v5", "codex-dom-v6",
        }
                and self.context is None):
            raise ValueError("versioned prompt requires bounded task context")
        duration = (self.deadline - self.created_at).total_seconds()
        if not 0 < duration <= 3600:
            raise ValueError("job deadline must be within the session duration")
        if (not self.consent.dom_transfer_accepted
                or self.consent_hash != content_hash(self.consent)):
            raise ValueError("DOM consent or consent hash invalid")
        if self.inputs.dom_bytes > self.consent.max_dom_bytes:
            raise ValueError("DOM input exceeds consent byte limit")
        has_image = self.inputs.screenshot_sha256 is not None
        if has_image != (self.inputs.screenshot_bytes is not None):
            raise ValueError("image hash and length must occur together")
        if has_image != (self.stage == "image"):
            raise ValueError("stage and image input mismatch")
        if has_image and not self.consent.raw_screenshot_transfer_accepted:
            raise ValueError("image stage requires separate image consent")
        return self


class CodexCandidate(ClosedModel):
    kind: Literal["click", "type", "scroll", "wait"]
    element_id: ElementId | None = None
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    delta_y: int | None = Field(default=None, ge=-2000, le=2000)
    duration_ms: int | None = Field(default=None, ge=100, le=10_000)
    confidence: float = Field(ge=0, le=1)
    expected_outcome: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def fields_match_action(self):
        target = {"element_id"} if self.element_id else {"x", "y"}
        required = {
            "click": target, "type": target | {"text"},
            "scroll": {"delta_y"}, "wait": {"duration_ms"},
        }[self.kind]
        present = {key for key in (
            "element_id", "x", "y", "text", "delta_y", "duration_ms",
        ) if getattr(self, key) is not None}
        if present != required:
            raise ValueError("candidate fields do not match action kind")
        return self


class CodexCandidates(ClosedModel):
    outcome: Literal["candidates"] = "candidates"
    candidates: tuple[CodexCandidate, ...] = Field(min_length=1, max_length=10)


class CodexNeedScreenshot(ClosedModel):
    outcome: Literal["need_screenshot"] = "need_screenshot"
    reason: Literal["insufficient_dom", "visual_target"]


class CodexStop(ClosedModel):
    outcome: Literal["stop"] = "stop"
    reason: Literal["complete", "no_safe_action", "unsupported_state"]


CodexOutput = Annotated[
    CodexCandidates | CodexNeedScreenshot | CodexStop, Field(discriminator="outcome"),
]


def parse_codex_output(data: bytes) -> CodexOutput:
    """Only unwrap the exact root-object schema envelope; reject every extra key."""
    value = json.loads(data)
    if isinstance(value, dict) and set(value) == {"result"}:
        value = value["result"]
    return TypeAdapter(CodexOutput).validate_python(value)


class CodexUsage(ClosedModel):
    input_tokens: int = Field(ge=0, le=1_000_000_000)
    output_tokens: int = Field(ge=0, le=1_000_000_000)
    cached_input_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000)


class CodexBridgeResponse(CodexScope):
    schema_version: Literal["v1"] = "v1"
    job_id: UUID
    bridge_id: UUID
    correlation_id: UUID
    request_sequence: int = Field(ge=1, le=10)
    observation_id: UUID
    snapshot_id: UUID
    state_fingerprint: Digest
    request_hash: Digest
    stage: Stage
    actual_model: Literal["gpt-6-luna"] | None
    cli_version: str = Field(pattern=r"^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$")
    started_at: AwareDatetime
    completed_at: AwareDatetime
    failure_code: FailureCode | None = None
    output: CodexOutput | None = None
    usage: CodexUsage | None = None

    @model_validator(mode="after")
    def valid_result(self):
        if (self.output is None) == (self.failure_code is None):
            raise ValueError("response requires exactly one output or failure code")
        if self.completed_at < self.started_at:
            raise ValueError("response time order invalid")
        if self.output and self.output.outcome == "need_screenshot" and self.stage != "dom":
            raise ValueError("image stage cannot request another screenshot")
        if self.output and self.output.outcome == "candidates" and self.stage == "dom":
            if any(c.kind in {"click", "type"} and c.element_id is None
                   for c in self.output.candidates):
                raise ValueError("DOM targets require element IDs")
        return self


class CodexBridgeReceipt(CodexScope):
    schema_version: Literal["v1"] = "v1"
    job_id: UUID
    bridge_id: UUID
    request_hash: Digest
    claim_nonce: UUID
    status: JobStatus
    recorded_at: AwareDatetime
    authorization_expires_at: AwareDatetime


class CodexBridgeReadiness(ClosedModel):
    busy: bool = False
    configured: bool = False
    online: bool = False
    authenticated: bool = False
    capabilities_qualified: bool = False
    model_access: Literal["unverified", "available", "unavailable"] = "unverified"
    failure_code: FailureCode | None = None

    @property
    def ready(self) -> bool:
        return (self.configured and self.online and self.authenticated
                and self.capabilities_qualified and self.failure_code is None
                and self.model_access != "unavailable")


class CodexBridgeEvent(ClosedModel):
    sequence: int = Field(ge=1, le=64)
    recorded_at: AwareDatetime
    job_id: UUID
    stage: Literal["claimed", "running", "completed", "failed", "cancelled", "expired"]
    usage: CodexUsage | None = None
