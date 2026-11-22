"""Closed v1 contracts for the local proposal bridge; never execution authority."""

import hashlib
import json
import re
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
    model_serializer,
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
# Local CLI bridge engines. Each provider is pinned to exactly one model; consent,
# requests and responses must all name the same provider.
BridgeProvider = Literal["codex_cli", "claude_cli"]
BridgeModel = Literal["gpt-6-luna", "claude-opus-5-5"]
BRIDGE_PROVIDER_MODELS: dict[str, str] = {
    "codex_cli": "gpt-6-luna", "claude_cli": "claude-opus-5-5",
}
BRIDGE_PROVIDERS = frozenset(BRIDGE_PROVIDER_MODELS)


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
    dom_transfer_provider: BridgeProvider | None = None
    max_dom_elements: int = Field(default=100, ge=1, le=100)
    max_dom_bytes: int = Field(default=65_536, ge=1024, le=65_536)

    @model_validator(mode="after")
    def consent(self):
        if self.dom_transfer_accepted != (self.dom_transfer_provider is not None):
            raise ValueError("DOM consent must be explicitly bound to a bridge provider")
        return self


class CodexConsentSnapshot(CodexInputPolicy):
    raw_screenshot_transfer_accepted: bool = False
    raw_screenshot_transfer_provider: BridgeProvider | None = None

    @model_validator(mode="after")
    def image_consent(self):
        if self.raw_screenshot_transfer_accepted != (
            self.raw_screenshot_transfer_provider is not None
        ):
            raise ValueError("image consent must be explicitly bound to a bridge provider")
        if (self.raw_screenshot_transfer_provider is not None
                and self.dom_transfer_provider is not None
                and self.raw_screenshot_transfer_provider != self.dom_transfer_provider):
            raise ValueError("image and DOM consent must name the same bridge provider")
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
    button_kind: Literal["native", "styled_link", "custom"] | None = None
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
    # Worker-owned geometry hint; never part of the model's observation payload.
    next_scroll_delta_y: int | None = Field(default=None, ge=1, le=2000)

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


AGENT_PROMPT_PATTERN = r"^agent-loop-v[1-9][0-9]*$"
AGENT_MEMORY_MAX_CHARS = 2000
AGENT_HISTORY_MAX_ITEMS = 5
AGENT_HISTORY_ITEM_MAX_CHARS = 600
AGENT_SNAPSHOT_MAX_CHARS = 24_000
AGENT_MAX_ACTIONS = 10
# UTF-8 byte ceiling of a whole agent request (canonical bytes, ensure_ascii=False).
AGENT_REQUEST_MAX_BYTES = 131_072


class AgentLoopContext(ClosedModel):
    """Everything the agent prompt may carry; history is rendered once by the control plane."""

    task: str = Field(min_length=1, max_length=4000)
    allowed_hosts: tuple[Annotated[str, Field(min_length=1, max_length=255)], ...] = Field(
        max_length=100,
    )
    memory: str = Field(default="", max_length=AGENT_MEMORY_MAX_CHARS)
    history: tuple[Annotated[str, Field(max_length=AGENT_HISTORY_ITEM_MAX_CHARS)], ...] = Field(
        default=(), max_length=AGENT_HISTORY_MAX_ITEMS,
    )
    snapshot_version: int = Field(ge=1, le=1_000_000)
    snapshot: str = Field(max_length=AGENT_SNAPSHOT_MAX_CHARS)


class CodexBridgeRequest(CodexScope):
    schema_version: Literal["v1"] = "v1"
    job_id: UUID
    bridge_id: UUID
    correlation_id: UUID
    request_sequence: int = Field(ge=1, le=20)
    observation_id: UUID
    snapshot_id: UUID
    state_fingerprint: Digest
    provider: BridgeProvider = "codex_cli"
    model: BridgeModel = "gpt-6-luna"
    prompt_version: str = Field(pattern=r"^(codex-dom|agent-loop)-v[1-9][0-9]*$")
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
    agent_context: AgentLoopContext | None = None

    @model_serializer(mode="wrap")
    def omit_absent_agent_context(self, handler):
        # Keeps the canonical bytes (and request hash) of every v4 job unchanged.
        data = handler(self)
        if data.get("agent_context") is None:
            data.pop("agent_context", None)
        return data

    @model_validator(mode="after")
    def valid_job(self):
        is_agent = re.fullmatch(AGENT_PROMPT_PATTERN, self.prompt_version) is not None
        if is_agent != (self.agent_context is not None):
            raise ValueError("agent prompt version and agent context must occur together")
        if is_agent and len(canonical_bytes(self)) > AGENT_REQUEST_MAX_BYTES:
            raise ValueError("agent request exceeds byte limit")
        if (self.prompt_version in {
            "codex-dom-v2", "codex-dom-v3", "codex-dom-v4", "codex-dom-v5", "codex-dom-v6",
            "codex-dom-v7", "codex-dom-v8", "codex-dom-v9", "codex-dom-v10", "codex-dom-v11",
        }
                and self.context is None):
            raise ValueError("versioned prompt requires bounded task context")
        if BRIDGE_PROVIDER_MODELS[self.provider] != self.model:
            raise ValueError("bridge provider and model mismatch")
        if self.consent.dom_transfer_provider != self.provider:
            raise ValueError("DOM consent is bound to another bridge provider")
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

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler.resolve_ref_schema(handler(core_schema))
        # The model validator is not represented by Pydantic's default schema.
        # Advertise the same per-action field combinations to proposal models.
        variants = []
        for kind, combinations in cls.action_fields().items():
            for active in combinations:
                properties = {"kind": {"const": kind}}
                for field in ("element_id", "x", "y", "text", "delta_y", "duration_ms"):
                    field_schema = schema["properties"][field]
                    properties[field] = (
                        next(item for item in field_schema["anyOf"] if item.get("type") != "null")
                        if field in active else {"type": "null"}
                    )
                variants.append({"properties": properties})
        schema["anyOf"] = variants
        return schema

    @staticmethod
    def action_fields():
        return {
            "click": ({"element_id"}, {"x", "y"}),
            "type": ({"element_id", "text"}, {"x", "y", "text"}),
            "scroll": ({"delta_y"},),
            "wait": ({"duration_ms"},),
        }

    @model_validator(mode="after")
    def fields_match_action(self):
        present = {key for key in (
            "element_id", "x", "y", "text", "delta_y", "duration_ms",
        ) if getattr(self, key) is not None}
        if present not in self.action_fields()[self.kind]:
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


AgentActionKind = Literal["click", "type", "scroll", "wait", "back", "close_popup", "navigate"]
# Format `version:n` is checked by the domain (fullmatch with this pattern -> `invalid_ref`),
# not at parse time, so one bad ref does not reject the whole step. Strict schema has no pattern.
AGENT_REF_PATTERN = r"^[0-9]+:[0-9]+$"
AgentRef = Annotated[str, Field(min_length=1, max_length=24)]

# Fields each kind carries (besides the optional expected_outcome). `navigate` has no field:
# it can only return to the session target, and `ref` is always null for it.
_AGENT_ACTION_FIELDS: dict[str, frozenset[str]] = {
    "click": frozenset({"ref"}),
    "type": frozenset({"ref", "text"}),
    "scroll": frozenset({"delta_y"}),
    "wait": frozenset({"duration_ms"}),
    "back": frozenset(),
    "close_popup": frozenset(),
    "navigate": frozenset(),
}


class AgentAction(ClosedModel):
    """Flat on purpose: a strict-mode JSON schema cannot express per-kind variants safely."""

    kind: AgentActionKind
    ref: AgentRef | None = None
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    delta_y: int | None = Field(default=None, ge=-2000, le=2000)
    duration_ms: int | None = Field(default=None, ge=100, le=10_000)
    expected_outcome: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def fields_match_kind(self):
        present = frozenset(
            key for key in ("ref", "text", "delta_y", "duration_ms")
            if getattr(self, key) is not None
        )
        if present != _AGENT_ACTION_FIELDS[self.kind]:
            raise ValueError("agent action fields do not match kind")
        return self


class AgentStep(ClosedModel):
    outcome: Literal["agent_step"] = "agent_step"
    evaluation_previous_goal: str = Field(min_length=1, max_length=500)
    memory: str = Field(max_length=AGENT_MEMORY_MAX_CHARS)
    next_goal: str = Field(min_length=1, max_length=500)
    actions: tuple[AgentAction, ...] = Field(min_length=1, max_length=AGENT_MAX_ACTIONS)


AgentLoopOutput = Annotated[
    AgentStep | CodexNeedScreenshot | CodexStop, Field(discriminator="outcome"),
]
# What a bridge response may carry: either family; `CodexOutput` itself never gains a variant.
BridgeOutput = Annotated[
    CodexCandidates | AgentStep | CodexNeedScreenshot | CodexStop, Field(discriminator="outcome"),
]


def parse_agent_output(data: bytes) -> AgentLoopOutput:
    """Same root-object envelope rule as `parse_codex_output`, for the agent family."""
    value = json.loads(data)
    if isinstance(value, dict) and set(value) == {"result"}:
        value = value["result"]
    return TypeAdapter(AgentLoopOutput).validate_python(value)


def agent_loop_output_schema() -> bytes:
    """Strict JSON schema for agent output: every field required (nullable), closed objects."""
    union = TypeAdapter(AgentLoopOutput).json_schema()
    definitions = union.pop("$defs")
    schema = {
        "type": "object", "properties": {"result": union}, "required": ["result"],
        "additionalProperties": False, "$defs": definitions,
    }

    def strict(node):
        if isinstance(node, dict):
            for key in ("default", "discriminator", "title"):
                node.pop(key, None)
            if "oneOf" in node:
                node["anyOf"] = node.pop("oneOf")
            if "const" in node:
                node["enum"] = [node.pop("const")]
            if "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for child in node.values():
                strict(child)
        elif isinstance(node, list):
            for child in node:
                strict(child)

    strict(schema)
    return json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()


class CodexUsage(ClosedModel):
    input_tokens: int = Field(ge=0, le=1_000_000_000)
    output_tokens: int = Field(ge=0, le=1_000_000_000)
    cached_input_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000)


class CodexBridgeResponse(CodexScope):
    schema_version: Literal["v1"] = "v1"
    job_id: UUID
    bridge_id: UUID
    correlation_id: UUID
    request_sequence: int = Field(ge=1, le=20)
    observation_id: UUID
    snapshot_id: UUID
    state_fingerprint: Digest
    request_hash: Digest
    stage: Stage
    actual_model: BridgeModel | None
    cli_version: str = Field(pattern=r"^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$")
    started_at: AwareDatetime
    completed_at: AwareDatetime
    failure_code: FailureCode | None = None
    output: BridgeOutput | None = None
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
    provider: BridgeProvider = "codex_cli"
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
