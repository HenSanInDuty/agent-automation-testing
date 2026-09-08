"""Deterministic Playwright source from verified evidence, never model-authored selectors."""

import json

from agents.generation.vision_plan import validate_selection
from auto_at.contracts.execution import validate_playwright_test_source
from auto_at.contracts.generation import GeneratedTestPlannerOutput, origin_for_url
from auto_at.contracts.vision import VisualLocatorDescriptor, VisualLocatorHandoff
from auto_at.contracts.vision_worker import VisualWorkerAction


def literal(value):
    return json.dumps(value, ensure_ascii=True)


def locator_expression(descriptor):
    descriptor = VisualLocatorDescriptor.model_validate(descriptor.model_dump())
    expression = "active"
    for scope in descriptor.scope:
        method = "frameLocator" if scope.kind == "iframe" else "locator"
        expression += f".{method}({literal(scope.selector)})"
    value = literal(descriptor.value)
    if descriptor.strategy == "role":
        return (
            expression + f".getByRole({literal(descriptor.role)}, {{ name: {value}, exact: true }})"
        )
    if descriptor.strategy == "label":
        return expression + f".getByLabel({value}, {{ exact: true }})"
    if descriptor.strategy == "test_id":
        return expression + f".getByTestId({value})"
    return expression + f".locator({value})"


def render_vision_source(selection, handoff, snapshot, actions, target_url):
    handoff = VisualLocatorHandoff.model_validate(handoff.model_dump())
    selection = validate_selection(selection, handoff)
    origin_for_url(target_url)
    operations = {o.id: o for o in snapshot["operations"]}
    locators = {item.id: item for item in snapshot["locators"]}
    source = ["import { test, expect } from '@playwright/test';"]
    operation_ids = []
    for branch in handoff.branches:
        if branch.status != "ready":
            continue
        source.extend(
            [
                f"test({literal('Observed branch ' + str(branch.id))}, async ({{ page }}) => {{",
                "  let active = page;",
            ]
        )
        previous = None
        for index, step in enumerate(branch.steps):
            operation = operations.get(step.operation_id)
            if (
                operation is None
                or operation.status != "completed"
                or operation.parent_operation_id != previous
                or operation.purpose not in {"setup", "explore"}
                or (operation.tenant_id, operation.project_id, operation.session_id)
                != (handoff.tenant_id, handoff.project_id, handoff.session_id)
                or operation.locator_id != step.locator_id
            ):
                raise ValueError("invalid_grounded_branch")
            previous = operation.id
            operation_ids.append(operation.id)
            if step.input_reference or operation.action_kind == "type":
                raise ValueError("input_binding_required")
            if index == 0:
                if operation.action_kind != "navigate" or operation.purpose != "setup":
                    raise ValueError("setup_unavailable")
                source.append(f"  await active.goto({literal(target_url)});")
                continue
            if operation.action_kind == "click":
                locator = locators.get(step.locator_id)
                if (
                    locator is None
                    or locator.status != "verified"
                    or not locator.descriptor
                    or locator.operation_id != operation.id
                    or locator.originating_frame_id != operation.actual_before_frame_id
                    or (locator.tenant_id, locator.project_id, locator.session_id)
                    != (handoff.tenant_id, handoff.project_id, handoff.session_id)
                ):
                    raise ValueError("locator_unavailable")
                variable = f"target{index}"
                source.append(f"  const {variable} = {locator_expression(locator.descriptor)};")
                # These are pre-action facts observed by the trusted locator verifier.
                source.extend(
                    [
                        f"  await expect({variable}).toBeVisible();",
                        f"  await expect({variable}).toBeEnabled();",
                    ]
                )
                popup = operation.before_page_id != operation.after_page_id
                if popup:
                    if not operation.before_page_id or not operation.after_page_id:
                        raise ValueError("page_identity_unavailable")
                    source.append(f"  const popup{index} = active.waitForEvent('popup');")
                source.append(f"  await {variable}.click();")
                if popup:
                    source.append(f"  active = await popup{index};")
            elif operation.action_kind in {"scroll", "wait"}:
                raw = actions.get(operation.proposal_id)
                if raw is None:
                    raise ValueError("action_parameters_unavailable")
                action = VisualWorkerAction.model_validate(
                    {
                        key: value
                        for key, value in raw.items()
                        if key not in {"confidence", "expected_outcome"}
                    }
                )
                if action.kind != operation.action_kind:
                    raise ValueError("action_parameters_mismatch")
                if action.kind == "scroll":
                    source.append(
                        f"  await active.mouse.wheel(0, {action.delta_y});"
                    )
                else:
                    source.append(f"  await active.waitForTimeout({action.duration_ms});")
            else:
                raise ValueError("unsupported_branch_action")
        source.append("});")
    text = "\n".join(source) + "\n"
    if len(text) > 100_000:
        raise ValueError("rendered_source_limit")
    validate_playwright_test_source(text)
    blocked = sum(branch.status == "blocked" for branch in handoff.branches)
    conditions = [
        "Observed visibility/actionability are preconditions; business outcomes remain unverified.",
        f"Excluded blocked branches: {blocked}; unresolved locators: {handoff.unresolved_count}.",
    ]
    return GeneratedTestPlannerOutput(
        title=selection.title,
        playwright_test_source=text,
        assumptions=selection.assumptions,
        stop_conditions=[*selection.stop_conditions[:48], *conditions],
    ), list(dict.fromkeys(operation_ids))
