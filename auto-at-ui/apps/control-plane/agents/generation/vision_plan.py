"""A bounded selection-only model call with strict evidence-reference validation."""

import json

from auto_at.contracts.generation import VisionGroundedPlannerOutput

from agents.generation.planner import PlannerOutputError, _json_object_content
from agents.prompts.vision_generation import SYSTEM_PROMPT


def planning_context(request, handoff):
    ready = [b for b in handoff.branches if b.status == "ready"]
    return {
        "redacted_request": request.redacted_request,
        "vision_source": request.vision_source.model_dump(mode="json"),
        "branches": [b.model_dump(mode="json") for b in handoff.branches],
        "allowed_assertions": [
            dict(
                branch_id=str(b.id),
                operation_id=str(s.operation_id),
                locator_id=str(s.locator_id),
                kind=kind,
            )
            for b in ready
            for s in b.steps
            if s.locator_id
            for kind in s.observation_codes
            if kind in {"visible", "enabled"}
        ],
        "output_schema": VisionGroundedPlannerOutput.model_json_schema(),
    }


def validate_selection(output, handoff):
    output = VisionGroundedPlannerOutput.model_validate(output.model_dump())
    ready = [b for b in handoff.branches if b.status == "ready"]
    if output.selected_branch_ids != [b.id for b in ready]:
        raise ValueError("selection_must_include_all_ready_branches_in_order")
    allowed = {
        (b.id, s.operation_id, s.locator_id, code)
        for b in ready
        for s in b.steps
        if s.locator_id
        for code in s.observation_codes
        if code in {"visible", "enabled"}
    }
    if any(
        (a.branch_id, a.operation_id, a.locator_id, a.kind) not in allowed
        for a in output.assertions
    ):
        raise ValueError("assertion_reference_unavailable")
    return output


async def plan_vision_test(model, request, handoff, max_tokens, max_evidence_bytes):
    content = json.dumps(planning_context(request, handoff), separators=(",", ":"))
    if len(content.encode()) > max_evidence_bytes:
        raise ValueError("handoff_evidence_budget")
    response = await model.ainvoke(
        {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        max_tokens=max_tokens,
    )
    try:
        output = VisionGroundedPlannerOutput.model_validate_json(
            _json_object_content(response["choices"][0]["message"]["content"])
        )
        return validate_selection(output, handoff)
    except (ValueError, KeyError, TypeError, IndexError):
        raise PlannerOutputError("invalid_vision_selection") from None
