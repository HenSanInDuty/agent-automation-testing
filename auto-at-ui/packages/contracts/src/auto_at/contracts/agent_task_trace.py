"""ADR-047 phase B1: the linear, immutable task trace of one completed agent-loop session.

`AgentTaskTrace` is the input of the deterministic source renderer. It is rebuilt on demand from
`visual_agent_steps` and the operation ledger (no table of its own), so it carries no clock, no
random id and no state of its own: building it twice from the same rows gives the same
`trace_hash`.

What a step holds: its place in the session (`step_index`, then the order of the step's operation
ids), the action kind, the verified locator descriptor, the controller-measured outcome, and for
`type` only `text_chars`. It never holds typed text, an agent `ref` (`version:n`), a coordinate or
a bounding box.

Contract decisions (phase 08):

* `wait` is KEPT. A completed `wait` is a real operation of the session, so the trace stays
  faithful to what ran, with its `duration_ms`. Whether the renderer emits it (a fixed sleep is a
  flaky test) is the renderer's decision: dropping a kept step later needs no new trace version,
  adding a dropped one would.
* Controller `setup` operations (navigate/refresh/wait outside every step) are NOT steps: the
  trace starts from `target_url`. Actions the batch skipped after an early stop have no operation
  id and are not steps either.
* `back` and `close_popup` have no stable Playwright equivalent, so a session using them is
  refused (`action_unsupported`) instead of silently producing a shorter chain.
* A session whose chain is not complete (a `worker_result_mismatch` step, an `explore` operation
  that belongs to no step, a missing or deleted frame, a missing operation) is refused with
  `evidence_unavailable`.
* The embedded `task_assessment` is the redacted copy stored with the session; it is advisory and
  never a verdict. Its free text (`summary`, `checks[].expectation`, `checks[].evidence`) is
  written by the model: the builder replaces every `digits:digits` token (an agent ref, and
  also a clock time) with `…`. KNOWN LIMIT for phases 11 and 14: the builder cannot remove a
  typed value the model quoted in that free text, because no typed value is stored anywhere to
  match it against. Those fields must not be rendered into generated source or shown as a
  trusted record without a decision on that.
  Exception (phase 10): `verified_text` holds page text verbatim, see `AgentTaskAssessmentCopy`.
  Whether its status allows a draft (`achieved` only, Q9) is the caller's rule.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from auto_at.contracts.codex_bridge import (
    AGENT_TASK_CHECKS_MAX,
    PAGE_TEXT_MAX_CHARS,
    AgentTaskCheck,
)
from auto_at.contracts.vision import Fingerprint, SafeCode, VisualLocatorDescriptor
from pydantic import BaseModel, ConfigDict, Field, model_validator

AGENT_TASK_TRACE_SCHEMA_VERSION = "v1"

AgentTaskActionKind = Literal["navigate", "click", "type", "scroll", "wait"]
TARGETED_KINDS = frozenset({"click", "type"})

# Why a trace cannot be built. The first six are the phase-08 set; `action_unsupported` is the one
# addition (see module docstring).
TraceRefusalCode = Literal[
    "assessment_unavailable",
    "evidence_unavailable",
    "operation_failed",
    "action_outcome_unknown",
    "locator_unavailable",
    "ephemeral_locator",
    "action_unsupported",
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AgentTaskFacts(_Closed):
    """Counts the controller measured over the step log (`action_facts`)."""

    actions_completed: int = Field(ge=0)
    actions_failed: int = Field(ge=0)
    actions_blocked_or_skipped: int = Field(ge=0)


VERIFIED_TEXT_ITEMS_MAX = 100
VERIFIED_TEXT_CHARS_MAX = PAGE_TEXT_MAX_CHARS  # the cap the worker applies to page text


class VerifiedTextItem(_Closed):
    # The page-text kinds of `CodexPageTextItem`, plus the name of a control.
    kind: Literal["alert", "status", "heading", "paragraph", "control_name"]
    text: str = Field(min_length=1, max_length=VERIFIED_TEXT_CHARS_MAX)
    check_index: int = Field(ge=0, lt=AGENT_TASK_CHECKS_MAX)
    # Phase 17 (F5): the text holds, or is part of, a value the agent typed in the session. The
    # requester may type another value later, so the renderer must not assert it. Only the flag is
    # kept, never the value. Absent in older sessions (False). A false flag is left out of every
    # dump, so the canonical payload, and with it `trace_hash`, is the one phase 16 computed.
    derived_from_typed: bool = Field(default=False, exclude_if=lambda flag: not flag)


class VerifiedText(_Closed):
    """Assertion candidates (phase 10): quotes of a `met` check that equal text the session saw."""

    items: tuple[VerifiedTextItem, ...] = Field(max_length=VERIFIED_TEXT_ITEMS_MAX)
    dropped: int = Field(ge=0)
    truncated: bool


class AgentTaskAssessmentCopy(_Closed):
    """Copy of the stored `task_assessment` (schema `v1`) of the session; advisory only.

    `verified_text` is optional (assessments stored before phase 10 lack it) and is the one field
    allowed to carry page text verbatim: it is text the controller observed on the page, used as
    an assertion value, and it is NOT redacted. It can equal a value the agent typed when that
    value is not sensitive (e.g. a todo title shown back on the page); the user accepted that for
    this field only (plan.md, 2026-11-27). It can never hold an agent ref: the model's quote must
    equal observed page text and refs are not page text.
    """

    schema_version: Literal["v1"]
    status: Literal["achieved", "not_achieved", "blocked", "inconclusive"]
    summary: str = Field(min_length=1, max_length=1000)
    checks: tuple[AgentTaskCheck, ...] = Field(max_length=AGENT_TASK_CHECKS_MAX)
    source: Literal["agent", "controller"]
    stop_reason: SafeCode
    facts: AgentTaskFacts
    advisory: Literal[True]
    verified_text: VerifiedText | None = None


class AgentTaskTraceOutcome(_Closed):
    """What the controller measured for one completed operation (never the agent's claim)."""

    outcome_code: SafeCode
    url_change: Literal["unchanged", "changed", "unavailable"]
    visual_change: Literal["unchanged", "changed", "unavailable"]


class AgentTaskTraceStep(_Closed):
    step_index: int = Field(ge=0)
    operation_id: UUID
    kind: AgentTaskActionKind
    locator_id: UUID | None = None
    # A verified, durable descriptor; `dom_path` is a live-node binding and is refused.
    locator: VisualLocatorDescriptor | None = None
    # `type` only: the length of the typed text. The text itself is never stored.
    text_chars: int | None = Field(default=None, ge=1, le=1000)
    delta_y: int | None = Field(default=None, ge=-2000, le=2000)
    duration_ms: int | None = Field(default=None, ge=100, le=10_000)
    outcome: AgentTaskTraceOutcome

    @model_validator(mode="after")
    def fields_match_kind(self) -> "AgentTaskTraceStep":
        targeted = self.kind in TARGETED_KINDS
        if targeted != (self.locator is not None and self.locator_id is not None):
            raise ValueError("click and type require a locator, other kinds forbid one")
        if self.locator is not None and self.locator.strategy == "dom_path":
            raise ValueError("ephemeral locator cannot be part of a task trace")
        present = {
            name
            for name in ("text_chars", "delta_y", "duration_ms")
            if getattr(self, name) is not None
        }
        expected = {
            "type": {"text_chars"},
            "scroll": {"delta_y"},
            "wait": {"duration_ms"},
        }.get(self.kind, set())
        if present != expected:
            raise ValueError("step parameters do not match its kind")
        return self


def _hash_of(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AgentTaskTrace(_Closed):
    schema_version: Literal["v1"] = AGENT_TASK_TRACE_SCHEMA_VERSION
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    session_id: UUID
    # Where the chain starts; the controller's `setup` navigation is not a step.
    target_url: str = Field(min_length=1, max_length=2000)
    intent_hash: Fingerprint
    task_assessment: AgentTaskAssessmentCopy
    steps: tuple[AgentTaskTraceStep, ...] = Field(min_length=1)
    trace_hash: Fingerprint

    def compute_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"trace_hash"})
        # `seal` calls this on an unvalidated model, so work on the dumped dict, not the field.
        if payload["task_assessment"].get("verified_text") is None:
            # An assessment without the key hashes exactly as it did before phase 10.
            payload["task_assessment"].pop("verified_text", None)
        return _hash_of(payload)

    @model_validator(mode="after")
    def validate_chain(self) -> "AgentTaskTrace":
        ids = [step.operation_id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("trace contains duplicate operations")
        indexes = [step.step_index for step in self.steps]
        if indexes != sorted(indexes):
            raise ValueError("trace steps must follow step_index order")
        if self.trace_hash != self.compute_hash():
            raise ValueError("trace_hash mismatch")
        return self

    @classmethod
    def seal(cls, **fields: Any) -> "AgentTaskTrace":
        """Validate `fields` (everything but `trace_hash`) and stamp the canonical hash."""
        unsealed = cls.model_construct(**fields, trace_hash="0" * 64)
        return cls.model_validate(
            unsealed.model_dump(mode="json", exclude={"trace_hash"})
            | {"trace_hash": unsealed.compute_hash()}
        )
