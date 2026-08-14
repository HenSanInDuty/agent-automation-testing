"""Bounded prompt and parsing boundary for generated Playwright Test drafts."""

from __future__ import annotations

import json
import re
from typing import Any

from auto_at.contracts.generation import GeneratedTestPlannerOutput, TestGenerationPlanningRequest
from pydantic import ValidationError

from agents.shared.models import LanguageModel

PROMPT_VERSION = "test-generation-v5"


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
    instructions = (
        "You are an advisory Playwright Test planner. The user's request may be in any language, "
        "including Vietnamese. Interpret its testing intent; the user does not need to know "
        "Playwright or this response schema. Return exactly one raw JSON object that validates "
        "against output_schema. Never use Markdown, code fences, prose, or fields other than "
        "title, playwright_test_source, assumptions, and stop_conditions; every required field "
        "must be present. Write a self-contained TypeScript test that imports only from "
        "@playwright/test and uses the supplied target_url. Do not use Node, shell, filesystem, "
        "process, package, direct-network, dynamic-import, eval, or credential APIs. Do not "
        "invent credentials, URLs, acceptance criteria, or project policy. Record uncertainty as "
        "assumptions or stop_conditions instead of claiming an unverified outcome. Translate "
        "natural-language intent into observable assertions. For a request to check <a> links "
        "and <button> controls, use only standard Playwright locator APIs: page.locator('a, "
        "button'), locator.count(), locator.nth(), locator.isVisible(), locator.isDisabled(), "
        "locator.getAttribute('href'), locator.click(), page.url(), and expect(). Do not use "
        "page.evaluate, locator.evaluate, JavaScript execution, fetch, or direct network APIs. "
        "Use two separate loops: one for page.locator('button') and one for "
        "page.locator('a[href]'). "
        "Never place a button click inside an href condition: a button has no href and must still "
        "be tested when visible and enabled. At the start of every loop iteration, navigate back "
        "to the supplied target_url and reacquire the locator by nth(index). Do not use "
        "page.goBack() or rely on a stale locator after a click changes the page. Visit the "
        "supplied URL, inspect "
        "every visible enabled button and every visible link with an href. Click each eligible "
        "control one at a time. Before clicking a link, read its href and resolve it against the "
        "current page URL with new URL(href, page.url()). Skip it when its resolved origin differs "
        "from target_url's origin, its protocol is not HTTP(S), or it is a fragment-only anchor; "
        "record that scope limit in stop_conditions. After every click, assert an observable "
        "result when the page exposes one, then navigate back to the supplied target_url before "
        "the next control. Skip responsive controls hidden at the current breakpoint. Use the "
        "element's text, aria-label, title, or href as a stable description when available. "
        "Assert a concrete observable post-click "
        "result when the page exposes one; otherwise state that limitation in stop_conditions. "
        "Do not claim a control worked merely because click() did not throw. Keep selectors "
        "and assertions resilient and bounded. Keep playwright_test_source under 1,200 characters. "
        "Use no comments, navigation waits, sleeps, or unused variables. This prevents "
        "the source from being cut off mid-test. Your response MUST match this JSON pattern "
        "exactly: "
        '{"title":"short test title","playwright_test_source":"import { test, expect } '
        'from \'@playwright/test\';\\n...","assumptions":["..."],"stop_conditions":["..."]}. '
        "Replace the example values, but keep exactly these four keys and their value types. "
        "Encode the full TypeScript source as one JSON string, escaping newlines as \\n and "
        "escaping quotes correctly; never emit TypeScript as a separate code block. Before sending "
        "your answer, internally verify that it is valid JSON, has no extra keys, has all four "
        "keys, and conforms to output_schema. If the intended test is uncertain, return valid "
        "JSON and describe the uncertainty in assumptions or stop_conditions."
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
