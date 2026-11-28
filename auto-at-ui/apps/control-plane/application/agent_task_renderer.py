"""ADR-047 phase B4: deterministic Playwright source from an `AgentTaskTrace`, no model involved.

The trace (phase 08) gives the ordered steps with their verified locators and, per `type` step, only
the typed length. The requester supplies the typed values (Q1); they go into the returned source and
nowhere else: not into the title, assumptions, stop conditions, error messages or error codes.
Selectors come only from the verified locators (Q2) and the result assertions only from the
candidates the controller matched against page text it observed (Q8, phase 10).
"""

from collections.abc import Sequence
from uuid import UUID

from auto_at.contracts.agent_task_trace import AgentTaskTrace, VerifiedTextItem
from auto_at.contracts.execution import validate_playwright_test_source
from auto_at.contracts.generation import GeneratedTestPlannerOutput, origin_for_url

from application.vision_source_renderer import literal, locator_expression

SOURCE_MAX_CHARS = 100_000  # `GeneratedTestPlannerOutput.playwright_test_source`
# A value stands in for a typed one while the culprit of a policy rejection is searched for.
_PLACEHOLDER = "x"


class AgentTaskRenderRefused(ValueError):
    """The trace cannot become source; `code` says why, the rest says where. Never holds a value."""

    def __init__(
        self,
        code: str,
        *,
        step_index: int | None = None,
        operation_id: UUID | None = None,
    ) -> None:
        super().__init__(code)
        self.code, self.step_index, self.operation_id = code, step_index, operation_id


def _locator(step) -> str:
    """The verified locator of a click/type step, or a refusal that names the step."""
    locator = step.locator
    if locator is None or locator.strategy == "dom_path":
        # The trace contract already forbids both; this guards a trace built around it.
        raise AgentTaskRenderRefused(
            "locator_unavailable", step_index=step.step_index, operation_id=step.operation_id
        )
    return locator_expression(locator)


def _assertion(item: VerifiedTextItem) -> str:
    text = literal(item.text)
    if item.kind == "control_name":
        # A control's accessible name may come from its label rather than its text.
        exact = "{ exact: true }"
        found = f"active.getByText({text}, {exact}).or(active.getByLabel({text}, {exact}))"
    else:
        found = f"active.getByText({text})"
    # `.first()`: the same text often shows twice (a list item and its toast); strict mode fails.
    return f"  await expect({found}.first()).toBeVisible();"


def _candidate_lines(trace: AgentTaskTrace) -> tuple[list[str], int, int]:
    """Assertion lines the source policy accepts, in observed order, and how many it left out.

    -> (lines, refused by the source policy, left out for holding a value typed in the session).
    The requester types the values of the draft, so a candidate that holds the agent's own typed
    value would stop matching the page as soon as the requester types another (phase 17, F5).
    """
    verified = trace.task_assessment.verified_text
    lines: list[str] = []
    refused = typed = 0
    for item in verified.items if verified else ():
        if item.derived_from_typed:
            typed += 1
            continue
        line = _assertion(item)
        try:
            validate_playwright_test_source(line)
        except ValueError:
            refused += 1  # page text such as "process" cannot be asserted in policy-checked source
            continue
        if line not in lines:
            lines.append(line)
    return lines, refused, typed


def _body(trace: AgentTaskTrace, values: Sequence[str], assertions: Sequence[str]) -> str:
    lines = [
        "import { test, expect } from '@playwright/test';",
        f"test({literal('Agent task ' + str(trace.session_id))}, async ({{ page }}) => {{",
        "  const active = page;",
        f"  await active.goto({literal(trace.target_url)});",
    ]
    remaining = iter(values)
    for position, step in enumerate(trace.steps):
        if step.kind == "navigate":
            lines.append(f"  await active.goto({literal(trace.target_url)});")
        elif step.kind in {"click", "type"}:
            variable = f"target{position}"
            lines.extend(
                [
                    f"  const {variable} = {_locator(step)};",
                    # Pre-action facts the trusted locator verifier observed in the session.
                    f"  await expect({variable}).toBeVisible();",
                    f"  await expect({variable}).toBeEnabled();",
                ]
            )
            if step.kind == "click":
                lines.append(f"  await {variable}.click();")
            else:
                lines.append(f"  await {variable}.fill({literal(next(remaining))});")
        elif step.kind == "scroll":
            lines.append(f"  await active.mouse.wheel(0, {step.delta_y});")
        else:  # wait; the trace type admits nothing else
            lines.append(f"  await active.waitForTimeout({step.duration_ms});")
    lines.extend(assertions)
    lines.append("});")
    return "\n".join(lines) + "\n"


def typed_steps(trace: AgentTaskTrace) -> list:
    """The `type` steps in the order their values are consumed: the one list `_check_values`, the
    policy search and `GET .../test-draft/inputs` all read, so they cannot disagree."""
    return [step for step in trace.steps if step.kind == "type"]


def _check_values(trace: AgentTaskTrace, values: Sequence[str]) -> None:
    typed = typed_steps(trace)
    for step, value in zip(typed, values, strict=False):
        if len(value) != step.text_chars:
            raise AgentTaskRenderRefused(
                "input_value_mismatch", step_index=step.step_index, operation_id=step.operation_id
            )
    if len(values) < len(typed):
        step = typed[len(values)]
        raise AgentTaskRenderRefused(
            "input_value_missing", step_index=step.step_index, operation_id=step.operation_id
        )
    if len(values) > len(typed):
        raise AgentTaskRenderRefused("input_value_mismatch")  # a value no step asked for


def _refuse_by_policy(trace: AgentTaskTrace, values: Sequence[str], assertions) -> None:
    """The finished source breaks the policy: say whether a typed value or something else did."""
    typed = typed_steps(trace)
    blank = [_PLACEHOLDER * len(value) for value in values]
    try:
        validate_playwright_test_source(_body(trace, blank, assertions))
    except ValueError:
        raise AgentTaskRenderRefused("source_policy_rejected") from None
    for index, step in enumerate(typed):
        one = [*blank[:index], values[index], *blank[index + 1 :]]
        try:
            validate_playwright_test_source(_body(trace, one, assertions))
        except ValueError:
            raise AgentTaskRenderRefused(
                "input_value_rejected_by_source_policy",
                step_index=step.step_index,
                operation_id=step.operation_id,
            ) from None
    # Only a combination of values trips it, so no single step is to blame.
    raise AgentTaskRenderRefused("input_value_rejected_by_source_policy")


def render_agent_task_source(
    trace: AgentTaskTrace, input_values: Sequence[str] = ()
) -> GeneratedTestPlannerOutput:
    """Pure and deterministic: the same trace and values give the same source and hash.

    `input_values` holds one value per `type` step, in step order; each must be exactly as long as
    the session's recorded `text_chars` (a matching length does not prove the value right: the run
    after approval is the evidence). Refusals raise `AgentTaskRenderRefused` with a code, never a
    value: `locator_unavailable`, `input_value_missing`, `input_value_mismatch`,
    `input_value_rejected_by_source_policy`, `source_policy_rejected`, `target_url_invalid`,
    `rendered_source_limit`.
    """
    try:
        origin_for_url(trace.target_url)
    except ValueError:
        raise AgentTaskRenderRefused("target_url_invalid") from None
    for step in trace.steps:  # name the first step without a usable locator before anything else
        if step.kind in {"click", "type"}:
            _locator(step)
    _check_values(trace, input_values)
    assertions, refused, typed_left_out = _candidate_lines(trace)
    text = _body(trace, input_values, assertions)
    if len(text) > SOURCE_MAX_CHARS:
        raise AgentTaskRenderRefused("rendered_source_limit")
    try:
        validate_playwright_test_source(text)
    except ValueError:
        _refuse_by_policy(trace, input_values, assertions)
    typed_count = sum(step.kind == "type" for step in trace.steps)
    return GeneratedTestPlannerOutput(
        title=f"Agent task test from session {trace.session_id}",
        playwright_test_source=text,
        assumptions=_assumptions(typed_count),
        stop_conditions=_stop_conditions(trace, len(assertions), refused, typed_left_out),
    )


def _assumptions(typed_count: int) -> list[str]:
    notes = [
        "Steps replay the recorded agent session in order; selectors come only from locators "
        "the worker verified during that session.",
        "Each control is checked visible and enabled before its action, as in the session.",
        "Waits replay the recorded duration; popups and new tabs are not tracked.",
    ]
    if typed_count:
        notes.append(
            f"{typed_count} typed value(s) were supplied by the requester when the draft was "
            "created and match the length the session recorded; the run after approval is the "
            "only evidence they are right."
        )
    return notes


def _stop_conditions(
    trace: AgentTaskTrace, asserted: int, refused: int, typed_left_out: int = 0
) -> list[str]:
    notes = ["The task assessment is advisory; only the run after approval gives a verdict."]
    if asserted:
        notes.append(
            f"Task outcome asserts only text the session observed: {asserted} assertion(s) "
            "on that text, nothing else about the result."
        )
    else:
        notes.append(
            "Task outcome is not asserted (kết quả task chưa được assert): no verified page "
            "text candidate exists, so the test only checks the controls are visible and enabled."
        )
    verified = trace.task_assessment.verified_text
    if verified is not None and (verified.dropped or verified.truncated):
        notes.append(
            f"Some quotes of the assessment were not verified against the page "
            f"(dropped {verified.dropped}, truncated {verified.truncated}) and are not asserted."
        )
    if refused:
        notes.append(f"{refused} candidate(s) were left out: the source policy refuses their text.")
    if typed_left_out:
        notes.append(
            f"{typed_left_out} candidate(s) were left out: their text holds a value typed in the "
            "session, and a result that contains a typed value is not asserted because the "
            "requester may type another one."
        )
    return notes


def has_test_values(trace: AgentTaskTrace) -> bool:
    """The `PlanningProvenance.contains_test_values` of a draft rendered from this trace."""
    return bool(typed_steps(trace))
