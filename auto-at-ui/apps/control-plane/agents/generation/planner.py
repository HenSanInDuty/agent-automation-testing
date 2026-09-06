"""Bounded prompt and parsing boundary for generated Playwright Test drafts."""

from __future__ import annotations

import json
import re
from typing import Any

from auto_at.contracts.generation import GeneratedTestPlannerOutput, TestGenerationPlanningRequest
from pydantic import ValidationError

from agents.prompts.generation import GENERATION_PLANNER_SYSTEM_PROMPT, PROMPT_VERSION
from agents.shared.models import LanguageModel

__all__ = [
    "PROMPT_VERSION",
    "PlannerOutputError",
    "build_planning_prompt",
    "parse_planner_response",
]


class PlannerOutputError(ValueError):
    """The model did not return the narrow response contract."""

    def __init__(self, diagnostic: str) -> None:
        super().__init__("planner returned malformed structured output")
        self.diagnostic = diagnostic


def build_planning_prompt(
    request: TestGenerationPlanningRequest, allowed_origins: list[str]
) -> dict[str, Any]:
    """Return the complete tool-less model payload, containing no raw request or secrets."""
    schema = GeneratedTestPlannerOutput.model_json_schema()
    instructions = GENERATION_PLANNER_SYSTEM_PROMPT
    context = {
        "target_url": request.target_url,
        "allowed_origins": allowed_origins,
        "redacted_request": request.redacted_request,
        "request_hash": request.request_hash,
        "output_schema": schema,
    }
    return {
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(context, separators=(",", ":"))},
        ],
        # The configured OpenRouter endpoint accepts JSON-object mode but has
        # no currently eligible endpoint for this model's strict JSON Schema
        # request. Response Healing repairs common JSON wrappers/syntax while
        # Pydantic still rejects missing or extra contract fields locally.
        "response_format": {"type": "json_object"},
        "plugins": [{"id": "response-healing"}],
        "temperature": 0,
    }


def parse_planner_response(response: Any) -> GeneratedTestPlannerOutput:
    """Accept only a JSON object from the provider's OpenAI-compatible response."""
    try:
        content = response["choices"][0]["message"]["content"]
        output = GeneratedTestPlannerOutput.model_validate_json(_json_object_content(content))
        return output.model_copy(
            update={
                "playwright_test_source": _normalize_source_newlines(
                    output.playwright_test_source
                )
            }
        )
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise PlannerOutputError("invalid_json") from error
    except ValidationError as error:
        kinds = sorted({str(item["type"]) for item in error.errors()})
        raise PlannerOutputError(f"invalid_contract:{','.join(kinds)}") from error


def _json_object_content(content: Any) -> str:
    """Normalize common OpenAI-compatible text envelopes without trusting their contents."""
    if isinstance(content, list):
        parts = [item.get("text") for item in content if isinstance(item, dict)]
        if not parts or not all(isinstance(part, str) for part in parts):
            raise TypeError("content does not contain text parts")
        content = "".join(parts)
    if not isinstance(content, str):
        raise TypeError("content is not a string")
    value = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", value, flags=re.IGNORECASE)
    if fenced:
        value = fenced.group(1)
    if not value.startswith("{") or not value.endswith("}"):
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise json.JSONDecodeError("expected a JSON object", value, 0)
        value = value[start : end + 1]
    return value


def _normalize_source_newlines(source: str) -> str:
    """Repair a provider double-escaping TypeScript line endings in its JSON value."""
    if "\n" not in source and r"\n" in source:
        return source.replace(r"\r\n", "\n").replace(r"\n", "\n")
    return source


async def plan_test(
    model: LanguageModel,
    request: TestGenerationPlanningRequest,
    allowed_origins: list[str],
    max_tokens: int,
) -> GeneratedTestPlannerOutput:
    response = await model.ainvoke(
        build_planning_prompt(request, allowed_origins), max_tokens=max_tokens
    )
    return parse_planner_response(response)
