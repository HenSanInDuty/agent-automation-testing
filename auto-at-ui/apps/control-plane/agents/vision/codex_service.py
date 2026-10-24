"""Validate the entire proposal batch before creating browser-action candidates."""

import json
import re

from auto_at.contracts.codex_bridge import (
    CodexBoundObservation,
    CodexOutput,
    CodexProposalBinding,
    CodexTaskContext,
)
from auto_at.contracts.vision import StopAction, VisualAction, validate_locator_value
from pydantic import TypeAdapter

from agents.shared.redaction import redact_value
from agents.vision.executor import VisualCandidateBatchOutcome


def task_context(intent: str, observed_actions: tuple[str, ...] = ()) -> CodexTaskContext:
    def redact(text: str):
        text = str(redact_value(text))
        text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[REDACTED]", text)
        text = re.sub(r"\b\d{7,}\b", "[REDACTED]", text)
        return text
    return CodexTaskContext(
        task_intent=redact(intent), observed_actions=tuple(redact(s) for s in observed_actions),
    )


def output_schema(max_candidates: int) -> bytes:
    if not 1 <= max_candidates <= 10:
        raise ValueError("invalid Codex candidate cap")
    union = TypeAdapter(CodexOutput).json_schema()
    definitions = union.pop("$defs")
    definitions["CodexCandidates"]["properties"]["candidates"]["maxItems"] = max_candidates
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


def validate_candidates(
    output: CodexOutput, bound: CodexBoundObservation, *, stage: str, max_candidates: int,
) -> VisualCandidateBatchOutcome:
    if output.outcome == "need_screenshot":
        raise ValueError("screenshot escalation belongs to the application")
    if output.outcome == "stop":
        return VisualCandidateBatchOutcome(
            status="completed", actions=[StopAction(confidence=1, expected_outcome=output.reason)],
            target_bindings=(None,), calls_used=0,
        )
    if not 1 <= len(output.candidates) <= max_candidates:
        raise ValueError("candidate cap exceeded")
    elements = {e.element_id: e for e in bound.observation.elements}
    bindings = {b.element_id: b for b in bound.bindings}
    actions, targets = [], []
    for candidate in output.candidates:
        validate_locator_value(candidate.expected_outcome)
        if candidate.text is not None:
            validate_locator_value(candidate.text)
            if redact_value(candidate.text) != candidate.text:
                raise ValueError("sensitive typed input")
        data = candidate.model_dump(exclude_none=True)
        element_id = data.pop("element_id", None)
        target = None
        if candidate.kind in {"click", "type"}:
            if element_id is None and stage != "image":
                raise ValueError("DOM action requires a bound element")
            if element_id is not None:
                element = elements.get(element_id)
                binding = bindings.get(element_id)
                if (element is None or binding is None or not element.enabled
                        or candidate.kind == "type" and not element.editable):
                    raise ValueError("ineligible or unknown DOM target")
                box = binding.bounds
                data["x"], data["y"] = box.x + box.width / 2, box.y + box.height / 2
                target = CodexProposalBinding(
                    observation_id=bound.observation.observation_id,
                    snapshot_id=bound.observation.snapshot_id, element_id=element_id,
                    state_fingerprint=bound.observation.state_fingerprint,
                    expected_descriptor=binding.descriptor,
                )
        actions.append(TypeAdapter(VisualAction).validate_python(data))
        targets.append(target)
    return VisualCandidateBatchOutcome(
        status="completed", actions=actions, target_bindings=tuple(targets), calls_used=0,
    )
