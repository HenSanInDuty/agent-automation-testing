"""Offline, synthetic bridge contracts: no subprocess, credential or provider access."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from auto_at.contracts.codex_bridge import (
    CodexBridgeRequest,
    CodexBridgeResponse,
    CodexCandidate,
    CodexConsentSnapshot,
    CodexDomElement,
    CodexDomObservation,
    canonical_bytes,
    content_hash,
)
from domain.codex_bridge import (
    validate_job_transition,
    validate_observation,
    validate_request_time,
    validate_response,
)

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)


def observation(**changes):
    return CodexDomObservation.model_validate(dict(
        tenant_id="fixture", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
        observation_id=uuid4(), snapshot_id=uuid4(), state_fingerprint="a" * 64,
        captured_at=NOW, viewport={"width": 1280, "height": 720}, elements=[{
            "element_id": "e_" + "a" * 32, "role": "button", "name": "Continue",
            "enabled": True, "editable": False,
        }],
    ) | changes)


def request(obs=None, **changes):
    obs = obs or observation()
    consent = CodexConsentSnapshot(dom_transfer_accepted=True, dom_transfer_provider="codex_cli")
    return CodexBridgeRequest.model_validate(dict(
        **{key: getattr(obs, key) for key in (
            "tenant_id", "project_id", "session_id", "fencing_token", "observation_id",
            "snapshot_id", "state_fingerprint",
        )},
        job_id=uuid4(), bridge_id=uuid4(), correlation_id=uuid4(), request_sequence=1,
        prompt_version="codex-dom-v1", stage="dom", created_at=NOW,
        deadline=NOW + timedelta(seconds=120), consent=consent,
        consent_hash=content_hash(consent), candidate_limit=3, inputs={
            "dom_sha256": content_hash(obs), "dom_bytes": len(canonical_bytes(obs)),
            "schema_sha256": "b" * 64, "schema_bytes": 100,
        },
    ) | changes)


def response(req, **changes):
    return CodexBridgeResponse.model_validate(dict(
        **{key: getattr(req, key) for key in (
            "job_id", "bridge_id", "tenant_id", "project_id", "session_id", "correlation_id",
            "fencing_token", "request_sequence", "observation_id", "snapshot_id",
            "state_fingerprint", "stage",
        )},
        request_hash=content_hash(req), actual_model="gpt-6-luna", cli_version="0.163.0",
        started_at=NOW, completed_at=NOW + timedelta(seconds=1),
        output={"outcome": "stop", "reason": "complete"},
    ) | changes)


def test_valid_dom_job_and_response_are_bound_to_observation():
    obs = observation()
    req = request(obs)
    validate_observation(req, obs)
    validate_response(req, response(req), now=NOW + timedelta(seconds=2))
    assert "descriptor" not in canonical_bytes(obs).decode()
    assert "screenshot.png" not in canonical_bytes(req).decode()


@pytest.mark.parametrize("version", [
    "codex-dom-v2", "codex-dom-v3", "codex-dom-v4", "codex-dom-v5", "codex-dom-v6",
])
def test_task_context_is_required_for_versioned_prompts(version):
    with pytest.raises(ValueError, match="bounded task context"):
        request(prompt_version=version)
    assert request(prompt_version=version, context={"task_intent": "Open fixture"}).context


@pytest.mark.parametrize("field,value", [
    ("job_id", uuid4()), ("bridge_id", uuid4()), ("tenant_id", "other"),
    ("project_id", uuid4()), ("session_id", uuid4()), ("correlation_id", uuid4()),
    ("fencing_token", 2), ("request_sequence", 2), ("observation_id", uuid4()),
    ("snapshot_id", uuid4()), ("state_fingerprint", "c" * 64),
    ("stage", "image"), ("request_hash", "d" * 64),
])
def test_response_identity_mismatches_never_pass(field, value):
    req = request()
    with pytest.raises(ValueError, match="mismatch"):
        validate_response(req, response(req, **{field: value}), now=NOW + timedelta(seconds=2))


@pytest.mark.parametrize("changes", [
    {"model": "other"}, {"tenant_id": "../tenant"}, {"job_id": "../../outside"},
    {"command": "anything"}, {"path": "C:/outside"}, {"environment": {}},
    {"consent_hash": "f" * 64}, {"stage": "image"}, {"candidate_limit": 11},
    {"deadline": NOW}, {"deadline": NOW + timedelta(hours=2)},
    {"created_at": NOW.replace(tzinfo=None)},
])
def test_request_rejects_untrusted_fields_models_paths_and_invalid_limits(changes):
    with pytest.raises(ValueError):
        request(**changes)


@pytest.mark.parametrize("now", [NOW - timedelta(seconds=1), NOW + timedelta(seconds=120)])
def test_request_must_be_current(now):
    with pytest.raises(ValueError):
        validate_request_time(request(), now)


def test_image_requires_independent_consent_and_cannot_reescalate():
    req = request()
    inputs = req.inputs.model_dump() | {"screenshot_sha256": "e" * 64, "screenshot_bytes": 100}
    with pytest.raises(ValueError, match="separate"):
        request(stage="image", inputs=inputs)
    consent = CodexConsentSnapshot(
        dom_transfer_accepted=True, dom_transfer_provider="codex_cli",
        raw_screenshot_transfer_accepted=True, raw_screenshot_transfer_provider="codex_cli",
    )
    image = request(
        stage="image", inputs=inputs, consent=consent, consent_hash=content_hash(consent),
    )
    with pytest.raises(ValueError, match="another screenshot"):
        response(image, output={"outcome": "need_screenshot", "reason": "insufficient_dom"})


@pytest.mark.parametrize("changes", [
    {"actual_model": "other"}, {"cli_version": "raw diagnostic/path"},
    {"failure_code": "arbitrary provider text"}, {"verdict": "passed"},
    {"failure_code": "bridge_offline"}, {"completed_at": NOW - timedelta(seconds=1)},
    {"output": {"outcome": "candidates", "candidates": [{
        "kind": "click", "x": 0.5, "y": 0.5, "confidence": 1, "expected_outcome": "Continue",
    }]}},
])
def test_response_rejects_untrusted_output(changes):
    with pytest.raises(ValueError):
        response(request(), **changes)


@pytest.mark.parametrize("changes", [
    {"selector": "button"}, {"text": "unexpected"}, {"x": 0.5, "y": 0.5},
    {"element_id": "../../file"}, {"confidence": float("nan")}, {"confidence": 1.1},
    {"kind": "navigate"}, {"expected_outcome": "x" * 1001},
])
def test_candidate_rejects_selectors_extraneous_fields_and_invalid_limits(changes):
    with pytest.raises(ValueError):
        CodexCandidate.model_validate(dict(
            kind="click", element_id="e_" + "a" * 32, confidence=0.9, expected_outcome="Continue",
        ) | changes)


def test_observation_bounds_duplicates_and_hash_binding():
    obs = observation()
    element = obs.elements[0].model_dump()
    for changes in ({"name": "x" * 121}, {"value": "secret"}, {"input_type": "password"}):
        with pytest.raises(ValueError):
            CodexDomElement.model_validate(element | changes)
    with pytest.raises(ValueError):
        observation(elements=[element] * 101)
    with pytest.raises(ValueError, match="duplicate"):
        observation(elements=[element] * 2)
    with pytest.raises(ValueError, match="hash"):
        validate_observation(request(obs), obs.model_copy(update={"truncated": True}))


@pytest.mark.parametrize("old,new", [
    ("completed", "running"), ("cancelled", "completed"), ("expired", "completed"),
    ("failed", "queued"), ("queued", "completed"), ("running", "claimed"),
])
def test_terminal_and_backward_job_transitions_are_rejected(old, new):
    with pytest.raises(ValueError):
        validate_job_transition(old, new)


def test_normal_lifecycle_and_cancellation():
    for old, new in (("queued", "claimed"), ("claimed", "running"),
                     ("running", "completed"), ("queued", "cancelled")):
        validate_job_transition(old, new)


def test_response_enforces_utf8_byte_limit_not_only_character_limits():
    req = request(max_output_bytes=1024)
    result = response(req, output={"outcome": "candidates", "candidates": [{
        "kind": "type", "element_id": "e_" + "a" * 32, "text": "界" * 500,
        "confidence": 1, "expected_outcome": "Enter fixture text",
    }]})
    with pytest.raises(ValueError, match="byte limit"):
        validate_response(req, result, now=NOW + timedelta(seconds=2))
