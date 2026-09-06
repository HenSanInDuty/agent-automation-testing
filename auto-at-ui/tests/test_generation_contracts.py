import pytest
from auto_at.contracts.execution import TestExecutionRequest as ExecutionRequest
from auto_at.contracts.execution import sha256_text
from auto_at.contracts.generation import (
    ProjectExecutionPolicy,
    canonical_origin,
    redact_generation_request,
    request_hash,
    validate_generated_execution_request,
)
from auto_at.contracts.generation import (
    TestGenerationPlanningRequest as PlanningRequest,
)
from pydantic import ValidationError


def test_policy_matches_canonical_http_origins() -> None:
    policy = ProjectExecutionPolicy(
        project_id="11111111-1111-4111-8111-111111111111",
        allowed_origins=["HTTPS://Example.Test:443/"],
    )

    assert policy.allowed_origins == ["https://example.test"]
    assert policy.allows("https://example.test/path")
    assert not policy.allows("https://other.test")


def test_wildcard_origin_policy_allows_every_http_destination() -> None:
    policy = ProjectExecutionPolicy(
        project_id="11111111-1111-4111-8111-111111111111",
        allowed_origins=["*"],
    )

    assert policy.allowed_origins == ["*"]
    assert policy.allows("https://example.test/path")
    assert policy.allows("http://another.example.test:8080/path")
    with pytest.raises(ValueError):
        policy.allows("file:///tmp/test")


@pytest.mark.parametrize("value", ["file:///tmp/test", "https://user:secret@example.test", "https://example.test/path"])
def test_origin_policy_rejects_non_origins_and_credentials(value: str) -> None:
    with pytest.raises(ValueError):
        canonical_origin(value)


def test_planning_text_is_redacted_and_hashed_before_it_is_stored() -> None:
    redacted = redact_generation_request("Log in with password: swordfish and check checkout")

    assert "swordfish" not in redacted
    assert PlanningRequest(
        correlation_id="889dfc9c-b50e-444a-a67b-e5ee56673fa5",
        project_id="11111111-1111-4111-8111-111111111111",
        target_url="https://example.test/",
        redacted_request=redacted,
        request_hash=request_hash(redacted),
    ).request_hash == request_hash(redacted)


def test_planning_contract_rejects_credentials_before_model_or_persistence_boundary() -> None:
    with pytest.raises(ValidationError, match="redacted"):
        PlanningRequest(
            correlation_id="889dfc9c-b50e-444a-a67b-e5ee56673fa5",
            project_id="11111111-1111-4111-8111-111111111111",
            target_url="https://user:secret@example.test",
            redacted_request="password: swordfish",
            request_hash="a" * 64,
        )


def test_planning_contract_rejects_a_hash_that_does_not_match_redacted_text() -> None:
    with pytest.raises(ValidationError, match="request_hash"):
        PlanningRequest(
            correlation_id="889dfc9c-b50e-444a-a67b-e5ee56673fa5",
            project_id="11111111-1111-4111-8111-111111111111",
            target_url="https://example.test/",
            redacted_request="Check checkout",
            request_hash="a" * 64,
        )


def test_generated_execution_is_checked_against_its_project_policy_and_source_hash() -> None:
    source = "import { test } from '@playwright/test';\ntest('home', async () => {});\n"
    request = ExecutionRequest(
        project_id="11111111-1111-4111-8111-111111111111",
        test_case_id="generated-home",
        target_type="web_ui",
        target_url="https://example.test/path",
        revision="a" * 40,
        runner_config={
            "mode": "playwright_test_source",
            "playwright_test_source": source,
            "source_hash": sha256_text(source),
        },
    )
    policy = ProjectExecutionPolicy(
        project_id="11111111-1111-4111-8111-111111111111",
        allowed_origins=["https://example.test"],
    )

    assert validate_generated_execution_request(request, policy).mode == "playwright_test_source"

    blocked_policy = policy.model_copy(update={"allowed_origins": ["https://other.test"]})
    with pytest.raises(ValueError, match="not allowed"):
        validate_generated_execution_request(request, blocked_policy)


@pytest.mark.parametrize(
    "source",
    [
        "import { readFile } from 'node:fs';",
        "const value = require('fs');",
        "await fetch('https://example.test');",
    ],
)
def test_generated_execution_rejects_prohibited_source(source: str) -> None:
    request = ExecutionRequest(
        project_id="11111111-1111-4111-8111-111111111111",
        test_case_id="generated-home",
        target_type="web_ui",
        target_url="https://example.test",
        revision="a" * 40,
        runner_config={
            "mode": "playwright_test_source",
            "playwright_test_source": source,
            "source_hash": sha256_text(source),
        },
    )
    policy = ProjectExecutionPolicy(
        project_id="11111111-1111-4111-8111-111111111111",
        allowed_origins=["https://example.test"],
    )

    with pytest.raises(ValidationError, match="prohibited|only"):
        validate_generated_execution_request(request, policy)
