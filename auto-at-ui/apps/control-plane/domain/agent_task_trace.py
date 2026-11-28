"""ADR-047 phase B1: pure builder of the linear task trace of a completed agent-loop session.

The handoff builder (`application/vision_handoff.py`) walks the operation tree, which turns an
agent session into disconnected `navigate -> action` branches and blocks every `type`; the real
order of an agent session lives in `visual_agent_steps.operation_ids` (spike phase 07,
`runner-r1.md` mục 1, 6). So the chain is `step_index`, then the order of the step's
`operation_ids`. Nothing here reads a database, a clock or a random source: the same rows always
give the same `trace_hash`.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from auto_at.contracts.agent_task_trace import (
    TARGETED_KINDS,
    AgentTaskAssessmentCopy,
    AgentTaskTrace,
    AgentTaskTraceOutcome,
    AgentTaskTraceStep,
    TraceRefusalCode,
)
from pydantic import ValidationError

# `back` and `close_popup` have no stable Playwright equivalent, so they are refused, not dropped.
_SUPPORTED_KINDS = frozenset({"navigate", "click", "type", "scroll", "wait"})
_NOT_COMPLETED = {
    "failed": "operation_failed",
    "rejected": "operation_failed",
    "unknown": "action_outcome_unknown",
    "prepared": "action_outcome_unknown",
    "executing": "action_outcome_unknown",
}


class AgentTaskTraceRefused(ValueError):
    """The evidence cannot support a trace; `code` says why, the rest says where."""

    def __init__(
        self,
        code: TraceRefusalCode,
        *,
        step_index: int | None = None,
        operation_id: UUID | None = None,
    ) -> None:
        super().__init__(code)
        self.code, self.step_index, self.operation_id = code, step_index, operation_id


def _executed(step) -> list[Mapping[str, Any]]:
    """Actions that ran; a skipped one (batch stopped early) has no `result` or operation id."""
    return [
        entry for entry in step.actions if "result" in entry and not entry.get("skipped_reason")
    ]


def _assessment(session) -> AgentTaskAssessmentCopy:
    stored = session.task_assessment
    if (
        session.exploration_engine != "agent_loop"
        or session.state != "completed"
        or not isinstance(stored, Mapping)
    ):
        raise AgentTaskTraceRefused("assessment_unavailable")
    try:
        copy = AgentTaskAssessmentCopy.model_validate(stored)
    except ValidationError:
        raise AgentTaskTraceRefused("assessment_unavailable") from None
    return _without_refs(copy)


# ponytail: ref-shaped means digits:digits anywhere in the text (the ref grammar is
# `AGENT_REF_PATTERN` in codex_bridge.py:421, a full match, so it cannot scan prose). A clock
# time like 12:30 is a false positive and is redacted too: the free text is advisory and losing
# it is cheaper than leaking a ref. The marker is one character so no field outgrows its limit.
_REF_SHAPE = re.compile(r"(?<!\d)\d+:\d+(?!\d)")
_REF_MARK = "…"


def _without_refs(copy: AgentTaskAssessmentCopy) -> AgentTaskAssessmentCopy:
    """The model writes free text in `summary` and `evidence`; no agent ref may survive in it.

    `verified_text` is copied as is, NOT stripped: its items are page text the controller
    matched verbatim and use as an assertion value, so masking `12:30` would break the
    assertion. A real agent ref cannot be there: a quote only becomes an item when it equals text
    the session observed (page text or a control name), and a ref is controller bookkeeping, not
    page text. If a page really shows `1:7`, that is the page's own text and the right assertion.
    """
    strip = lambda text: _REF_SHAPE.sub(_REF_MARK, text)  # noqa: E731
    data = copy.model_dump(mode="json")
    data["summary"] = strip(data["summary"])
    for check in data["checks"]:
        check["expectation"] = strip(check["expectation"])
        check["evidence"] = strip(check["evidence"])
    return AgentTaskAssessmentCopy.model_validate(data)


def _trace_step(step_index, operation, entry, locators, live_frames) -> AgentTaskTraceStep:
    """One verified step, or the refusal naming this operation."""

    def refuse(code: TraceRefusalCode) -> AgentTaskTraceRefused:
        return AgentTaskTraceRefused(code, step_index=step_index, operation_id=operation.id)

    if operation.status != "completed":
        raise refuse(_NOT_COMPLETED[operation.status])
    kind = operation.action_kind
    if kind not in _SUPPORTED_KINDS:
        raise refuse("action_unsupported")
    if entry.get("kind") != kind:
        raise refuse("evidence_unavailable")
    locator = None
    if kind in TARGETED_KINDS:
        locator = locators.get(operation.locator_id)
        if locator is None or locator.status != "verified" or locator.descriptor is None:
            raise refuse("locator_unavailable")
    frames = (operation.actual_before_frame_id, operation.actual_after_frame_id)
    if not all(frame_id in live_frames for frame_id in frames):
        raise refuse("evidence_unavailable")
    if locator is not None and locator.descriptor.strategy == "dom_path":
        # A live-node binding serves this advisory session, not a durable test across reloads.
        raise refuse("ephemeral_locator")
    try:
        return AgentTaskTraceStep(
            step_index=step_index,
            operation_id=operation.id,
            kind=kind,
            locator_id=locator.id if locator else None,
            locator=locator.descriptor if locator else None,
            # Only the length of typed text was ever stored; `ref` and coordinates are not copied.
            text_chars=entry.get("text_chars"),
            delta_y=entry.get("delta_y"),
            duration_ms=entry.get("duration_ms"),
            outcome=AgentTaskTraceOutcome(
                outcome_code=operation.outcome_code,
                url_change=operation.url_change,
                visual_change=operation.visual_change,
            ),
        )
    except ValidationError:
        raise refuse("evidence_unavailable") from None


def build_agent_task_trace(
    session, steps: Iterable, operations: Iterable, locators: Iterable, frames: Iterable
) -> AgentTaskTrace:
    """Build the trace from rows already read: session record, step log, and the trace snapshot."""
    assessment = _assessment(session)
    by_id = {operation.id: operation for operation in operations}
    locator_by_id = {locator.id: locator for locator in locators}
    live_frames = {frame.metadata.id for frame in frames if not frame.metadata.deleted_at}
    seen: set[UUID] = set()
    built: list[AgentTaskTraceStep] = []
    for step in sorted(steps, key=lambda item: item.step_index):
        if step.stop_reason == "worker_result_mismatch":
            # The worker's answer did not match the intent, so the operation is not in the step.
            raise AgentTaskTraceRefused("evidence_unavailable", step_index=step.step_index)
        try:
            operation_ids = [UUID(str(item)) for item in step.operation_ids]
        except ValueError:
            raise AgentTaskTraceRefused(
                "evidence_unavailable", step_index=step.step_index
            ) from None
        executed = _executed(step)
        if len(executed) != len(operation_ids):
            raise AgentTaskTraceRefused("evidence_unavailable", step_index=step.step_index)
        for entry, operation_id in zip(executed, operation_ids, strict=True):
            operation = by_id.get(operation_id)
            reported = (entry["result"] or {}).get("operation_id")
            if (
                operation is None
                or operation_id in seen
                or (reported is not None and str(reported) != str(operation_id))
            ):
                raise AgentTaskTraceRefused(
                    "evidence_unavailable", step_index=step.step_index, operation_id=operation_id
                )
            seen.add(operation_id)
            if operation.purpose == "setup":
                continue  # the controller's own navigation, outside every step
            if operation.purpose != "explore":
                raise AgentTaskTraceRefused(
                    "evidence_unavailable", step_index=step.step_index, operation_id=operation_id
                )
            built.append(
                _trace_step(step.step_index, operation, entry, locator_by_id, live_frames)
            )
    for operation in sorted(by_id.values(), key=lambda item: item.sequence):
        if operation.purpose == "explore" and operation.id not in seen:
            # An executed action that no step recorded: the chain is not complete.
            raise AgentTaskTraceRefused("evidence_unavailable", operation_id=operation.id)
    if not built:
        raise AgentTaskTraceRefused("evidence_unavailable")
    try:
        return AgentTaskTrace.seal(
            tenant_id=session.tenant_id,
            project_id=session.project_id,
            session_id=session.id,
            target_url=session.target_url,
            intent_hash=session.intent_hash,
            task_assessment=assessment,
            steps=tuple(built),
        )
    except ValidationError:
        # e.g. a target_url over the contract limit: the row cannot be a trace.
        raise AgentTaskTraceRefused("evidence_unavailable") from None
