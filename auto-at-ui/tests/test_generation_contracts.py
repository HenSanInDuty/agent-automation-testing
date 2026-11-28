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


def test_vision_provenance_is_optional_and_idempotency_includes_handoff_identity():
    from uuid import uuid4

    from auto_at.contracts.generation import (
        PlanningProvenance,
        VisionPlanningSource,
        vision_generation_key,
    )

    legacy = PlanningProvenance(provider="fixture", model="fixture", prompt_version="v1",
                                redaction_policy_version="v1")
    assert legacy.vision_source is None
    source = VisionPlanningSource(session_id=uuid4(), handoff_id=uuid4(), handoff_hash="a" * 64)
    key = vision_generation_key(source, "Explore")
    assert key == vision_generation_key(source, "Explore")
    for changes in ({"handoff_id": uuid4()}, {"handoff_hash": "b" * 64}, {"session_id": uuid4()}):
        assert key != vision_generation_key(source.model_copy(update=changes), "Explore")
    with pytest.raises(ValidationError):
        VisionPlanningSource(session_id=uuid4(), handoff_id=uuid4())


# ADR-047 phase 11: additive agent-trace provenance
_LEGACY_PROVENANCE = {
    "provider": "fixture",
    "model": "fixture",
    "prompt_version": "v1",
    "redaction_policy_version": "v1",
    "vision_source": None,
    "selected_branch_ids": [],
    "operation_ids": [],
}


def test_provenance_stored_before_the_agent_trace_fields_still_validates_unchanged():
    from auto_at.contracts.generation import PlanningProvenance

    old = PlanningProvenance.model_validate(_LEGACY_PROVENANCE)
    assert (old.agent_trace_source, old.contains_test_values) == (None, None)
    assert (old.owned_test_target, old.requested_by) == (None, None)
    # the old fields keep their shape: a draft written before this change reads back equal
    dumped = old.model_dump(mode="json")
    assert {key: dumped[key] for key in _LEGACY_PROVENANCE} == _LEGACY_PROVENANCE
    assert PlanningProvenance.model_validate(dumped) == old


def test_agent_trace_provenance_carries_only_identity_hash_and_flags():
    from uuid import uuid4

    from auto_at.contracts.generation import AgentTraceSource, PlanningProvenance

    session = uuid4()
    provenance = PlanningProvenance(
        **_LEGACY_PROVENANCE
        | {
            "agent_trace_source": AgentTraceSource(session_id=session, trace_hash="a" * 64),
            "contains_test_values": True,
            "owned_test_target": True,
            "requested_by": "actor-1",
        }
    )
    dumped = provenance.model_dump(mode="json")
    assert dumped["agent_trace_source"] == {"session_id": str(session), "trace_hash": "a" * 64}
    assert PlanningProvenance.model_validate(dumped) == provenance
    assert PlanningProvenance.model_validate_json(provenance.model_dump_json()) == provenance


@pytest.mark.parametrize(
    "bad",
    [
        {"session_id": "not-a-uuid", "trace_hash": "a" * 64},
        {"session_id": "00000000-0000-4000-8000-000000000001", "trace_hash": "a" * 63},
        {"session_id": "00000000-0000-4000-8000-000000000001", "trace_hash": "A" * 64},
        {"session_id": "00000000-0000-4000-8000-000000000001"},
        {"trace_hash": "a" * 64},
        {
            "session_id": "00000000-0000-4000-8000-000000000001",
            "trace_hash": "a" * 64,
            "summary": "free text does not belong here",
        },
    ],
)
def test_agent_trace_source_is_closed_and_hash_checked(bad):
    from auto_at.contracts.generation import AgentTraceSource

    with pytest.raises(ValidationError):
        AgentTraceSource.model_validate(bad)


@pytest.mark.parametrize(
    "extra", [{"requested_by": ""}, {"requested_by": "x" * 201}, {"unknown": 1}]
)
def test_provenance_still_refuses_unknown_keys_and_empty_requester(extra):
    from auto_at.contracts.generation import PlanningProvenance

    with pytest.raises(ValidationError):
        PlanningProvenance.model_validate(_LEGACY_PROVENANCE | extra)


def test_a_draft_with_agent_trace_provenance_keeps_its_source_hash_check():
    from uuid import uuid4

    from auto_at.contracts.generation import GeneratedTestDraft

    source = "import { test } from '@playwright/test';\n"
    fields = {
        "planning_request_id": uuid4(),
        "correlation_id": uuid4(),
        "title": "Agent task",
        "playwright_test_source": source,
        "provenance": _LEGACY_PROVENANCE
        | {
            "agent_trace_source": {"session_id": str(uuid4()), "trace_hash": "c" * 64},
            "contains_test_values": False,
        },
    }
    draft = GeneratedTestDraft(**fields, source_hash=sha256_text(source))
    assert draft.provenance.agent_trace_source.trace_hash == "c" * 64
    with pytest.raises(ValidationError):
        GeneratedTestDraft(**fields, source_hash="0" * 64)
    legacy = GeneratedTestDraft(
        **fields | {"provenance": _LEGACY_PROVENANCE}, source_hash=sha256_text(source)
    )
    assert legacy.provenance.agent_trace_source is None
