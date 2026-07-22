"""Executable fixtures lock the Python/TypeScript execution boundary at v1."""

import json
from pathlib import Path

from auto_at.contracts.execution import (
    TestExecutionRequest as ExecutionRequest,
)
from auto_at.contracts.execution import (
    TestExecutionResult as ExecutionResult,
)

FIXTURE_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "packages" / "contracts" / "fixtures" / "execution-v1"
)


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def test_web_ui_request_fixture_validates_against_execution_contract_v1() -> None:
    request = ExecutionRequest.model_validate(load_fixture("request.web-ui.json"))

    assert request.contract_version == "v1"
    assert request.target_type == "web_ui"
    assert request.runner_config["browser"] == "chromium"


def test_passed_result_fixture_validates_against_execution_contract_v1() -> None:
    result = ExecutionResult.model_validate(load_fixture("result.passed.json"))

    assert result.contract_version == "v1"
    assert result.status == "passed"
    assert result.artifacts[0].content_type == "application/zip"
