"""API-only loop tests; no Docker, provider, browser or external target calls."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

DIRECTORY = Path(__file__).parents[1] / "benchmark/vision/accuracy"
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location("accuracy_run", DIRECTORY / "run.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.remove(str(DIRECTORY))

POLICY = {"expected_provider": "codex_cli", "expected_model": "gpt-6-luna",
          "expected_input_policy_fingerprint": "a" * 64}


def test_download_evidence_filters_secrets_scope_and_malformed_records():
    from evidence import export_download_destination

    session, operation = str(uuid4()), str(uuid4())
    row = {"event": "vision.download.destinations", "session_id": session,
           "operation_id": operation, "destination_hashes": ["a" * 64],
           "status": "completed", "truncated": False, "url": "private-query-value"}
    exported = export_download_destination(row, session)
    assert exported == {**{key: row[key] for key in (
        "session_id", "operation_id", "destination_hashes", "status", "truncated",
    )}, "navigation_chain": []}
    for change in ({"session_id": str(uuid4())}, {"operation_id": "bad-id"},
                   {"destination_hashes": ["https://private.invalid"]},
                   {"destination_hashes": ["a" * 64] * 9}, {"truncated": "false"},
                   {"navigation_chain": [{"url_sha256": "https://private.invalid"}]},
                   {"navigation_chain": [{}] * 33}):
        assert export_download_destination({**row, **change}, session) is None
    chain = [{"url_sha256": "a" * 64, "redirected_from_sha256": "b" * 64,
              "url": "private-query-value"}]
    assert "private-query-value" not in json.dumps(export_download_destination(
        {**row, "navigation_chain": chain}, session,
    ))

ORACLE = {"schema_version": "vision-accuracy-oracle-v1", "examples": [
    {"id": "button", "expected": True, "action_kind": "click",
     "reference_path": "html > button:nth-of-type(1)", "outcome": {"kind": "navigation"}},
]}


class FakeAPI:
    def __init__(self):
        self.session = str(uuid4())
        self.operation = str(uuid4())
        self.locator = str(uuid4())
        self.frame = str(uuid4())
        self.calls = []
        self.timeout_once = False
        self.state = "unavailable"
        self.block_status = None
        self.bad_frame = False
        self.missing_frame = False
        self.active = False
        self.operation_status = "rejected"
        self.operation_purpose = "restore"
        self.operation_action = "wait"
        self.frame_bytes = b"synthetic-frame-content"

    def __call__(self, request):
        self.calls.append(request)
        if self.block_status:
            return httpx.Response(self.block_status, json={"detail": "private-provider-message"})
        path = request.url.path
        if path.endswith("/reload"):
            if self.timeout_once:
                self.timeout_once = False
                raise httpx.ReadTimeout("private-timeout", request=request)
            return httpx.Response(202, json={"id": self.session, "state": "queued"})
        if path.endswith("/explorations"):
            return httpx.Response(200, json={"items": [{"state": "running"}] if self.active
                                            else []})
        if path.endswith("/result"):
            return httpx.Response(200, json={
                "schema_version": "v1", "session_id": self.session,
                "exploration_state": self.state, "completion_reason": "state_restore_failed",
                "private_form": "private-secret", "exploration_report": {"conclusion": {
                    "status": "partial", "coverage": "not_established", "private": "private-secret",
                    "control_kinds": {"custom": 1},
                }},
            })
        if path.endswith("/trace"):
            frame = {"id": self.frame, "checksum": hashlib.sha256(self.frame_bytes).hexdigest(),
                     "byte_count": len(self.frame_bytes), "availability": "retained"}
            return httpx.Response(200, json={
                "schema_version": "v1", "session_id": self.session, "revision": "a" * 64,
                "next_sequence": 1, "has_more": False, "items": [{
                    "id": self.operation, "sequence": 1, "status": self.operation_status,
                    "purpose": self.operation_purpose, "action_kind": self.operation_action,
                    "outcome_code": "state_mismatch",
                    "before": frame, "after": frame, "private_value": "private-secret",
                    "locator_id": self.locator,
                }], "locators": [{"id": self.locator, "operation_id": self.operation,
                                   "status": "verified", "descriptor": {
                                       "strategy": "dom_path",
                                       "value": "html > button:nth-of-type(1)",
                                   }, "private": "private-secret"}],
            })
        if "/operation-frames/" in path:
            if self.missing_frame:
                return httpx.Response(404)
            return httpx.Response(200, content=b"bad" if self.bad_frame else self.frame_bytes)
        return httpx.Response(200, json={"id": self.session, "state": self.state,
                                        "safe_failure_reason": "state_restore_failed"})


@pytest.fixture
def setup_loop(tmp_path):
    api = FakeAPI()
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(api),
                      headers={"Authorization": "Bearer private-secret"}) as client:
        yield module.Loop(client, tmp_path / "runs"), api


def start(loop):
    return loop.start(str(uuid4()), ORACLE, POLICY, candidate_hash="source")


def test_timeout_after_submit_resumes_same_idempotency_key_and_keeps_failed_run(setup_loop):
    loop, api = setup_loop
    iteration = start(loop)
    api.timeout_once = True
    with pytest.raises(httpx.ReadTimeout):
        loop.resume(iteration)
    _, manifest = loop.manifest(iteration)
    assert manifest["session_id"] is None
    with pytest.raises(ValueError, match="resume unresolved"):
        start(loop)
    assert loop.resume(iteration)["session_id"] == api.session
    posts = [r for r in api.calls if r.method == "POST"]
    assert len(posts) == 2
    assert posts[0].headers["Idempotency-Key"] == posts[1].headers["Idempotency-Key"]
    assert all(r.url.path.endswith("/reload") for r in posts)


@pytest.mark.parametrize("status", [401, 403, 409, 429, 503])
def test_access_policy_quota_failures_never_change_policy_or_create_another_run(setup_loop, status):
    loop, api = setup_loop
    iteration = start(loop)
    api.block_status = status
    with pytest.raises(httpx.HTTPStatusError):
        loop.resume(iteration)
    assert len(list(loop.directory.glob("*/manifest.json"))) == 1
    assert not any(r.method in {"PUT", "DELETE", "PATCH"} for r in api.calls)
    assert "private" not in (loop.directory / iteration / "manifest.json").read_text()


def test_running_session_is_not_terminal_and_no_live_overlap(setup_loop):
    loop, api = setup_loop
    api.active = True
    with pytest.raises(ValueError, match="active exploration"):
        start(loop)
    api.active = False
    iteration = start(loop)
    api.state = "running"
    loop.resume(iteration)
    with pytest.raises(ValueError, match="not terminal"):
        loop.collect(iteration)


def test_collection_is_idempotent_filters_secrets_and_joins_diagnostics(setup_loop):
    loop, api = setup_loop
    iteration = start(loop)
    loop.resume(iteration)
    diagnostic = {"session_id": api.session, "operation_id": api.operation,
                  "failure_stage": "before_dispatch", "code": "state_mismatch",
                  "interaction_changed": True, "privateForms": "private-secret"}
    evidence = loop.collect(iteration, diagnostics=[diagnostic, {**diagnostic,
                                                               "session_id": str(uuid4())}])
    assert evidence == loop.collect(iteration)
    assert evidence["runtime_conclusion"] == {"status": "partial", "coverage": "not_established"}
    assert evidence["diagnosis"]["categories"][0]["category"] == "before_dispatch"
    assert len(evidence["diagnostics"]) == 1
    assert not evidence["diagnosis"]["physical_retry_authorized"]
    assert "private" not in json.dumps(evidence)
    assert "Bearer" not in json.dumps(evidence)


def test_frame_integrity_and_missing_evidence_are_not_success(setup_loop):
    loop, api = setup_loop
    iteration = start(loop)
    loop.resume(iteration)
    evidence = loop.collect(iteration)
    metadata = evidence["operations"][0]["after"]
    assert loop.frame(iteration, metadata) == api.frame_bytes
    api.bad_frame = True
    with pytest.raises(ValueError, match="integrity"):
        loop.frame(iteration, metadata)
    api.missing_frame = True
    with pytest.raises(httpx.HTTPStatusError):
        loop.frame(iteration, metadata)


def test_hash_schema_and_omitted_failed_operations_are_rejected(setup_loop):
    loop, api = setup_loop
    iteration = start(loop)
    loop.resume(iteration)
    loop.collect(iteration)
    detection = module.Detection(oracle_hash=module.content_hash(ORACLE),
                                 identified_ids=("button",), inventory_complete=True)
    with pytest.raises(ValueError, match="every operation"):
        loop.evaluate(iteration, [], detection)
    oracle_path = loop.directory / iteration / "oracle.json"
    module.write_json(oracle_path, {**ORACLE, "changed": True}, replace=True)
    with pytest.raises(ValueError, match="oracle changed"):
        loop.evaluate(iteration, [], detection)
    manifest_path, manifest = loop.manifest(iteration)
    module.write_json(manifest_path, {**manifest, "schema_version": "unknown"}, replace=True)
    with pytest.raises(ValueError, match="unknown manifest"):
        loop.manifest(iteration)


def test_stale_lock_file_does_not_block_restart_and_live_lock_prevents_two_writers(setup_loop):
    loop, _ = setup_loop
    (loop.directory / ".writer.lock").write_bytes(b"stale")
    with loop.locked():
        with pytest.raises(OSError), loop.locked():
            pytest.fail("second writer acquired lock")
    assert start(loop)


def test_historical_import_is_read_only_and_ineligible_for_qualification(setup_loop):
    loop, api = setup_loop
    iteration = loop.start(api.session, ORACLE, POLICY, candidate_hash="current", existing=True)
    assert loop.manifest(iteration)[1]["source_hash"] == "historical_unverified"
    assert not loop.manifest(iteration)[1]["qualification_eligible"]
    loop.collect(iteration)
    assert all(r.method == "GET" for r in api.calls)


def test_correctness_requires_real_binding_frames_and_content_addressed_outcome_review(setup_loop):
    loop, api = setup_loop
    api.operation_status = "completed"
    api.operation_purpose, api.operation_action = "explore", "click"
    iteration = start(loop)
    loop.resume(iteration)
    loop.collect(iteration)
    digest = module.content_hash(ORACLE)
    checksum = hashlib.sha256(api.frame_bytes).hexdigest()
    assessment = module.Assessment(
        operation_id=api.operation, oracle_hash=digest, target_id="button", status="completed",
        purpose="explore", action_kind="click", target_verdict="correct", outcome_verdict="correct",
        before_checksum=checksum, after_checksum=checksum, binding_reference=api.locator,
        review_method="fixture_oracle", outcome_reference="invented-proof",
    )
    detection = module.Detection(oracle_hash=digest, identified_ids=("button",),
                                 inventory_complete=True)
    with pytest.raises(ValueError, match="content-addressed"):
        loop.evaluate(iteration, [assessment], detection)
    review = module.OutcomeReview(
        operation_id=api.operation, oracle_hash=digest, outcome_kind="navigation",
        verdict="correct", review_method="fixture_oracle", before_checksum=checksum,
        after_checksum=checksum, finding="Synthetic fixture navigation oracle matched.",
    )
    reference = loop.record_review(iteration, review)
    assessment = assessment.model_copy(update={"outcome_reference": reference})
    assert loop.evaluate(iteration, [assessment], detection)["passed"]
    assert loop.evaluate(iteration, [assessment], detection)["passed"]
    with pytest.raises(ValueError, match="rewrites operation"):
        loop.evaluate(iteration, [assessment.model_copy(update={"status": "rejected"})], detection)
