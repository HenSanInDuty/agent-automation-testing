"""Bounded prompt and parsing boundary for generated Playwright Test drafts."""

from __future__ import annotations

import json
from typing import Any

from auto_at.contracts.generation import GeneratedTestPlannerOutput, TestGenerationPlanningRequest
from pydantic import ValidationError

from agents.shared.models import LanguageModel

PROMPT_VERSION = "test-generation-v1"


class PlannerOutputError(ValueError):
    """The model did not return the narrow response contract."""


def build_planning_prompt(
    request: TestGenerationPlanningRequest, allowed_origins: list[str]
) -> dict[str, Any]:
    """Return the complete tool-less model payload, containing no raw request or secrets."""
    schema = GeneratedTestPlannerOutput.model_json_schema()
    instructions = (
        "You are an advisory Playwright Test planner. Return JSON only matching the schema. "
        "Write a self-contained TypeScript test that imports only @playwright/test. "
        "Do not use Node, shell, filesystem, process, package, or direct network APIs. "
        "Do not invent credentials, acceptance criteria, URLs, or policy. "
        "Use the supplied target URL and describe uncertainty in assumptions or stop_conditions."
    )
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
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }


def parse_planner_response(response: Any) -> GeneratedTestPlannerOutput:
    """Accept only a JSON object from the provider's OpenAI-compatible response."""
    try:
        content = response["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("content is not a string")
        return GeneratedTestPlannerOutput.model_validate_json(content)
    except (IndexError, KeyError, TypeError, ValidationError, ValueError) as error:
        raise PlannerOutputError("planner returned malformed structured output") from error


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
