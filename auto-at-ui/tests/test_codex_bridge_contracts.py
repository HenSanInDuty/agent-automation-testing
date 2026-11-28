"""Offline, synthetic bridge contracts: no subprocess, credential or provider access."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

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


def test_scan_stride_is_private_bounded_and_legacy_optional():
    from auto_at.contracts.codex_bridge import CodexBoundObservation

    empty = observation(elements=[])
    old = CodexBoundObservation(observation=empty, bindings=[])
    assert old.next_scroll_delta_y is None
    current = CodexBoundObservation(observation=empty, bindings=[], next_scroll_delta_y=50)
    assert current.next_scroll_delta_y == 50
    assert b"next_scroll_delta_y" not in canonical_bytes(current.observation)
    assert canonical_bytes(old.observation) == canonical_bytes(current.observation)
    for invalid in [0, -1, 2001]:
        with pytest.raises(ValueError):
            CodexBoundObservation(observation=empty, bindings=[], next_scroll_delta_y=invalid)


@pytest.mark.parametrize("sequence", [11, 20])
def test_expanded_call_budget_preserves_request_response_binding(sequence):
    req = request(request_sequence=sequence)
    validate_response(req, response(req), now=NOW + timedelta(seconds=2))
    with pytest.raises(ValueError):
        request(request_sequence=21)
    with pytest.raises(ValueError):
        response(req, request_sequence=21)


@pytest.mark.parametrize("version", [
    "codex-dom-v2", "codex-dom-v3", "codex-dom-v4", "codex-dom-v5", "codex-dom-v6",
    "codex-dom-v7", "codex-dom-v8", "codex-dom-v9",
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


def test_observation_without_page_text_keeps_its_canonical_bytes_and_hash():
    # Hash computed with the contract as of HEAD d7d2b06 (before page text existed), fixed ids.
    obs = CodexDomObservation.model_validate(dict(
        tenant_id="fixture", project_id=UUID(int=1), session_id=UUID(int=2), fencing_token=1,
        observation_id=UUID(int=3), snapshot_id=UUID(int=4), state_fingerprint="a" * 64,
        captured_at=NOW, viewport={"width": 1280, "height": 720}, elements=[{
            "element_id": "e_" + "a" * 32, "role": "button", "name": "Continue",
            "enabled": True, "editable": False,
        }], unsupported=["closed_shadow"],
    ))
    assert content_hash(obs) == (
        "2b10cadeb97a2aabd4d4c6118399430949297d5722fc7319a25e615e2f353d78"
    )
    assert not {"page_text", "page_text_truncated", "page_text_skipped"} & obs.model_dump(
        mode="json").keys()
    # Explicit defaults serialize the same as absent fields.
    explicit = CodexDomObservation.model_validate(
        obs.model_dump() | {"page_text": [], "page_text_truncated": False, "page_text_skipped": 0})
    assert canonical_bytes(explicit) == canonical_bytes(obs)


def test_page_text_is_serialized_only_when_present_and_changes_the_hash():
    items = [{"kind": "alert", "text": "Sai mật khẩu"}, {"kind": "heading", "text": "Đăng nhập"}]
    plain, rich = observation(), observation(page_text=items, page_text_skipped=1)
    dumped = rich.model_dump(mode="json")
    assert dumped["page_text"] == items and dumped["page_text_skipped"] == 1
    assert "page_text_truncated" not in dumped
    assert content_hash(plain) != content_hash(rich)
    assert observation(page_text_truncated=True).model_dump(mode="json")["page_text_truncated"]


@pytest.mark.parametrize("text", [
    "Liên hệ nguoi.dung@example.com", "password=abc", "Reset password", "token abc",
    "https://example.com/x", "Mã 1234567", " leading", "line\nbreak", "x" * 161,
])
def test_page_text_rejects_sensitive_or_unbounded_text(text):
    with pytest.raises(ValueError):
        observation(page_text=[{"kind": "paragraph", "text": text}])


def test_page_text_bounds_items_kinds_and_total_bytes():
    with pytest.raises(ValueError):
        observation(page_text=[{"kind": "paragraph", "text": "a"}] * 25)
    with pytest.raises(ValueError):
        observation(page_text=[{"kind": "link", "text": "a"}])
    with pytest.raises(ValueError):
        observation(page_text=[{"kind": "paragraph", "text": "a", "value": "x"}])
    ok = [{"kind": "paragraph", "text": "a" * 160}] * 25
    observation(page_text=ok[:24])  # 24 * 160 = 3840 bytes, within the 4096 cap
    wide = [{"kind": "paragraph", "text": "ế" * 160}] * 10  # 3 bytes each: 4800 bytes
    with pytest.raises(ValueError, match="byte limit"):
        observation(page_text=wide)


PAGE_TEXT_SAMPLES = json.loads((
    Path(__file__).parents[1] / "packages/contracts/fixtures/vision-page-text-v1/samples.json"
).read_text(encoding="utf-8"))["samples"]


@pytest.mark.parametrize("sample", PAGE_TEXT_SAMPLES, ids=lambda s: s["text"][:20])
def test_page_text_filter_parity_with_the_worker(sample):
    # worker_keeps is asserted by vision-agent-mode.spec.ts on this file; here: kept => accepted.
    try:
        observation(page_text=[{"kind": "paragraph", "text": sample["text"]}])
        accepted = True
    except ValueError:
        accepted = False
    assert accepted == sample["python_accepts"]
    assert accepted or not sample["worker_keeps"]


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
