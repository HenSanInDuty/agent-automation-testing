"""Prompt-contract tests for natural-language generated-test planning."""

import json
from uuid import uuid4

import pytest
from agents.generation.planner import (
    PROMPT_VERSION,
    PlannerOutputError,
    build_planning_prompt,
    parse_planner_response,
)
from auto_at.contracts.generation import TestGenerationPlanningRequest, request_hash
from config import Settings


def test_generation_prompt_guides_vietnamese_link_and_button_requests() -> None:
    user_request = "Kiểm tra tính khả dụng của các thẻ <a> và <button>."
    request = TestGenerationPlanningRequest(
        id=uuid4(),
        correlation_id=uuid4(),
        project_id=uuid4(),
        target_url="https://example.test",
        redacted_request=user_request,
        request_hash=request_hash(user_request),
    )

    prompt = build_planning_prompt(request, ["https://example.test"])
    system_message = prompt["messages"][0]["content"]
    context = json.loads(prompt["messages"][1]["content"])

    assert PROMPT_VERSION == "test-generation-v5"
    assert Settings().agent_generation_prompt_version == PROMPT_VERSION
    assert "including Vietnamese" in system_message
    assert "one raw JSON object" in system_message
    assert "<a> links and <button> controls" in system_message
    assert "page.locator('a, button')" in system_message
    assert "locator.getAttribute('href')" in system_message
    assert "page.evaluate" in system_message
    assert "protocol is not HTTP(S), or it is a fragment-only anchor" in system_message
    assert "two separate loops" in system_message
    assert "Never place a button click inside an href condition" in system_message
    assert "Do not use page.goBack()" in system_message
    assert "new URL(href, page.url())" in system_message
    assert "Skip responsive controls hidden" in system_message
    assert "MUST match this JSON pattern exactly" in system_message
    assert "escaping newlines" in system_message
    assert "under 1,200 characters" in system_message
    assert "has no extra keys" in system_message
    assert context["redacted_request"] == user_request
    assert prompt["response_format"] == {"type": "json_object"}
    assert prompt["plugins"] == [{"id": "response-healing"}]


def test_planner_response_accepts_a_json_object_wrapped_in_markdown() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        "```json\n"
                        '{"title":"Buttons","playwright_test_source":'
                        '"import { test } from \'@playwright/test\';",'
                        '"assumptions":[],"stop_conditions":[]}\n'
                        "```"
                    )
                }
            }
        ]
    }

    assert parse_planner_response(response).title == "Buttons"


def test_planner_response_defaults_optional_review_metadata() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"title":"Buttons","playwright_test_source":'
                        '"import { test } from \'@playwright/test\';"}'
                    )
                }
            }
        ]
    }

    output = parse_planner_response(response)

    assert output.assumptions == []
    assert output.stop_conditions == []


def test_planner_response_normalizes_double_escaped_typescript_newlines() -> None:
    source = "import { test } from '@playwright/test';\\\\ntest('buttons', async () => {});"
    response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "title": "Buttons",
                            "playwright_test_source": source,
                            "assumptions": [],
                            "stop_conditions": [],
                        }
                    )
                }
            }
        ]
    }

    assert "\\n" not in parse_planner_response(response).playwright_test_source


def test_planner_response_rejects_extra_fields_without_logging_the_content() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"title":"Buttons","playwright_test_source":"x",'
                        '"assumptions":[],"stop_conditions":[],"unsafe":"x"}'
                    )
                }
            }
        ]
    }

    with pytest.raises(PlannerOutputError, match="malformed") as error:
        parse_planner_response(response)

    assert error.value.diagnostic == "invalid_contract:extra_forbidden"
