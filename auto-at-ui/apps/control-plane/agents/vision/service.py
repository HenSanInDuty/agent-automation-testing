"""Prompt framing and strict action parsing for untrusted visual model output."""

from json import loads
from re import DOTALL, fullmatch

from auto_at.contracts.vision import VisualAction
from pydantic import TypeAdapter, ValidationError

from agents.prompts.vision import (
    VISION_PROMPT_VERSION,
    build_visual_action_prompt,
    build_visual_candidate_batch_prompt,
)
from agents.vision.diagnostics import VisualDiagnosticCode, VisualDiagnosticFailure

__all__ = [
    "VISION_PROMPT_VERSION",
    "build_visual_action_prompt",
    "build_visual_candidate_batch_prompt",
    "validate_visual_action_output",
    "validate_visual_candidate_batch_output",
]

_ACTION_ADAPTER = TypeAdapter(VisualAction)
_ACTION_LIST_ADAPTER = TypeAdapter(list[VisualAction])


def validate_visual_action_output(content: str) -> VisualAction:
    """Normalize a provider envelope, then enforce the versioned action contract."""
    if not isinstance(content, str):
        raise ValueError("model returned invalid visual action JSON")
    value = _json_value(content)
    if (
        isinstance(value, dict)
        and set(value) == {"action"}
        and isinstance(value["action"], dict)
    ):
        value = value["action"]
    try:
        return _ACTION_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise ValueError("model returned an invalid visual action") from error


def validate_visual_candidate_batch_output(content: str, max_candidates: int) -> list[VisualAction]:
    """Strictly validate a provider reply before it can expand a BFS state."""
    value = _json_value(content)
    if not isinstance(value, dict) or set(value) != {"candidates"}:
        raise VisualDiagnosticFailure(VisualDiagnosticCode.INVALID_ROOT_SHAPE)
    try:
        candidates = _ACTION_LIST_ADAPTER.validate_python(value["candidates"])
    except ValidationError as error:
        raise VisualDiagnosticFailure(VisualDiagnosticCode.INVALID_CANDIDATE_SCHEMA) from error
    if not candidates:
        raise VisualDiagnosticFailure(VisualDiagnosticCode.EMPTY_CANDIDATES)
    if len(candidates) > max_candidates:
        raise VisualDiagnosticFailure(VisualDiagnosticCode.CANDIDATE_LIMIT_EXCEEDED)
    return candidates


def _json_value(content: str):
    """Normalize a sole Markdown fence without accepting arbitrary provider envelopes."""
    if not isinstance(content, str):
        raise VisualDiagnosticFailure(VisualDiagnosticCode.INVALID_JSON)
    normalized = content.strip()
    fenced = fullmatch(r"```(?:json)?\s*(.*?)\s*```", normalized, flags=DOTALL)
    if fenced is not None:
        normalized = fenced.group(1)
    try:
        return loads(normalized)
    except (TypeError, ValueError) as error:
        raise VisualDiagnosticFailure(VisualDiagnosticCode.INVALID_JSON) from error
