"""Offline `claude_cli` bridge checks: no subprocess, credential or provider access."""

import asyncio
import base64
import json
from datetime import UTC, datetime

import pytest
import test_codex_bridge_service as service_tests
import test_codex_bridge_spool as spool_tests
from agents.prompts.claude_bridge import SYSTEM_PROMPT
from agents.shared.runtime import VisionPolicy
from auto_at.contracts.codex_bridge import (
    CodexBridgeReadiness,
    CodexConsentSnapshot,
    CodexInputPolicy,
    content_hash,
)
from domain.codex_bridge import BridgeProcessResult
from infrastructure.codex_bridge.claude_process import (
    ClaudeEventReader,
    ClaudeProcess,
    ProcessRejected,
    bridge_environment,
    claude_command,
    claude_input,
    enforceable_schema,
    read_token,
)
from test_codex_bridge_contracts import request as codex_request

published = spool_tests.published
MODEL = "claude-opus-5-5"
SCHEMA = json.dumps({"type": "object", "properties": {"result": {"type": "object"}},
                     "required": ["result"], "additionalProperties": False}).encode()


def claude_request(**changes):
    consent = CodexConsentSnapshot(dom_transfer_accepted=True, dom_transfer_provider="claude_cli")
    return codex_request(**{
        "provider": "claude_cli", "model": MODEL, "consent": consent,
        "consent_hash": content_hash(consent), **changes,
    })


def line(event):
    return json.dumps(event).encode()


INIT = {"type": "system", "subtype": "init", "tools": ["StructuredOutput"],
        "mcp_servers": [], "model": MODEL}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "stop_reason": "tool_use",
          "structured_output": {"result": {"outcome": "stop", "reason": "complete"}},
          "usage": {"input_tokens": 3, "cache_read_input_tokens": 10,
                    "cache_creation_input_tokens": 5, "output_tokens": 7}}


def assistant(*blocks, model=MODEL):
    return {"type": "assistant", "message": {"model": model, "content": list(blocks)}}


# Contracts and policy


def test_claude_request_binds_provider_model_and_consent():
    req = claude_request()
    assert (req.provider, req.model) == ("claude_cli", MODEL)
    with pytest.raises(ValueError, match="provider and model"):
        claude_request(model="gpt-6-luna")
    codex_consent = CodexConsentSnapshot(
        dom_transfer_accepted=True, dom_transfer_provider="codex_cli",
    )
    with pytest.raises(ValueError, match="another bridge provider"):
        codex_request(provider="claude_cli", model=MODEL, consent=codex_consent,
                      consent_hash=content_hash(codex_consent))


def test_image_consent_cannot_name_a_different_bridge_provider():
    with pytest.raises(ValueError, match="same bridge provider"):
        CodexConsentSnapshot(
            dom_transfer_accepted=True, dom_transfer_provider="claude_cli",
            raw_screenshot_transfer_accepted=True, raw_screenshot_transfer_provider="codex_cli",
        )
    with pytest.raises(ValueError):
        CodexInputPolicy(dom_transfer_accepted=True, dom_transfer_provider=None)


def test_enabled_claude_policy_requires_claude_bound_dom_consent():
    claude = CodexInputPolicy(dom_transfer_accepted=True, dom_transfer_provider="claude_cli")
    policy = VisionPolicy(enabled=True, provider="claude_cli", model=MODEL, codex=claude)
    assert policy.codex.dom_transfer_provider == "claude_cli"
    codex = CodexInputPolicy(dom_transfer_accepted=True, dom_transfer_provider="codex_cli")
    with pytest.raises(ValueError):
        VisionPolicy(enabled=True, provider="claude_cli", model=MODEL, codex=codex)
    with pytest.raises(ValueError):
        VisionPolicy(provider="claude_cli", model="gpt-6-luna")


def test_existing_codex_request_hash_is_unchanged_by_generalization():
    # Historical jobs are hashed; codex defaults must serialize exactly as before.
    req = codex_request()
    assert (req.provider, req.model) == ("codex_cli", "gpt-6-luna")
    assert CodexBridgeReadiness().provider == "codex_cli"


# Command, input and environment


def test_command_disables_every_claude_code_capability():
    argv = claude_command("/usr/local/bin/claude", claude_request(), SCHEMA)
    joined = " ".join(argv)
    assert argv[:2] == ["/usr/local/bin/claude", "-p"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert argv[argv.index("--model") + 1] == MODEL
    assert argv[argv.index("--system-prompt") + 1] == SYSTEM_PROMPT
    assert json.loads(argv[argv.index("--json-schema") + 1]) == json.loads(SCHEMA)
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in argv
    for forbidden in ("dangerously", "bypass", "--add-dir", "--allowedTools", "acceptEdits"):
        assert forbidden not in joined


def test_input_puts_screenshot_before_prompt_only_for_image_stage(tmp_path):
    (tmp_path / "screenshot.png").write_bytes(b"\x89PNG synthetic")
    dom = json.loads(claude_input(claude_request(), tmp_path, b"prompt"))
    assert [b["type"] for b in dom["message"]["content"]] == ["text"]
    image_request = claude_request().model_copy(update={"stage": "image"})
    content = json.loads(claude_input(image_request, tmp_path, b"prompt"))["message"]["content"]
    assert [b["type"] for b in content] == ["image", "text"]
    assert base64.b64decode(content[0]["source"]["data"]) == b"\x89PNG synthetic"


def test_environment_carries_only_the_bridge_token(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-leak")
    environment = bridge_environment("oat-synthetic")
    assert environment["CLAUDE_CODE_OAUTH_TOKEN"] == "oat-synthetic"
    assert "ANTHROPIC_API_KEY" not in environment and environment["HOME"] == "/bridge-home"


def test_token_file_must_be_a_plain_non_empty_file(tmp_path):
    assert read_token(str(tmp_path / "missing")) is None
    (tmp_path / "empty").write_text(" \n")
    assert read_token(str(tmp_path / "empty")) is None
    (tmp_path / "token").write_text("oat-synthetic\n")
    assert read_token(str(tmp_path / "token")) == "oat-synthetic"


# Event validation


def test_reader_accepts_structured_output_and_trailing_state_event():
    reader = ClaudeEventReader()
    for event in (INIT, assistant({"type": "thinking", "thinking": ""},
                                  {"type": "tool_use", "id": "t1", "name": "StructuredOutput"}),
                  {"type": "user", "message": {"content": [
                      {"type": "tool_result", "tool_use_id": "t1"}]}},
                  {"type": "rate_limit_event"}, RESULT,
                  {"type": "system", "subtype": "session_state_changed"}):
        reader.event(line(event))
    assert reader.output == RESULT["structured_output"]
    assert reader.actual_model == MODEL
    assert (reader.usage.input_tokens, reader.usage.cached_input_tokens,
            reader.usage.output_tokens) == (18, 10, 7)


@pytest.mark.parametrize(("events", "code"), [
    ([{**INIT, "tools": ["StructuredOutput", "Bash"]}], "bridge_tool_rejected"),
    ([{**INIT, "mcp_servers": [{"name": "x"}]}], "bridge_tool_rejected"),
    ([{**INIT, "model": "claude-other"}], "bridge_model_unavailable"),
    ([INIT, assistant({"type": "tool_use", "id": "t", "name": "Bash"})], "bridge_tool_rejected"),
    ([INIT, assistant({"type": "server_tool_use", "id": "t"})], "bridge_tool_rejected"),
    ([INIT, assistant({"type": "text", "text": ""}, model="claude-other")],
     "bridge_model_unavailable"),
    ([INIT, {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "unknown"}]}}], "bridge_tool_rejected"),
    ([assistant({"type": "text", "text": ""})], "bridge_malformed_output"),
    ([INIT, {**RESULT, "is_error": True, "subtype": "error", "api_error_status": 401}],
     "bridge_login_required"),
    ([INIT, {**RESULT, "is_error": True, "subtype": "error", "api_error_status": 529}],
     "bridge_provider_unavailable"),
    ([INIT, {**RESULT, "stop_reason": "refusal"}], "bridge_provider_unavailable"),
    ([INIT, {**RESULT, "structured_output": None}], "bridge_malformed_output"),
    ([INIT, RESULT, assistant({"type": "text", "text": ""})], "bridge_malformed_output"),
])
def test_reader_rejections(events, code):
    reader = ClaudeEventReader()
    with pytest.raises(ProcessRejected) as rejected:
        for event in events:
            reader.event(line(event))
    assert rejected.value.code == code


def test_reader_rejects_non_json():
    with pytest.raises(ProcessRejected) as rejected:
        ClaudeEventReader().event(b"not json")
    assert rejected.value.code == "bridge_malformed_output"


def test_process_refuses_codex_requests_and_missing_token(tmp_path):
    process = ClaudeProcess("/usr/local/bin/claude", str(tmp_path / "missing"))
    result = asyncio.run(process.run(codex_request(), tmp_path, b"p", lambda: None))
    expected = "bridge_model_unavailable" if process_supported() else "bridge_cli_unsupported"
    assert result.failure_code == expected


def process_supported():
    import os

    return os.name == "posix"


# Bridge service and readiness


class RecordingProcess:
    def __init__(self):
        self.calls = 0

    async def run(self, *_args):
        self.calls += 1
        return BridgeProcessResult(failure_code="bridge_provider_unavailable")


def test_bridge_never_runs_a_job_for_another_engine(published):
    spool, req = published  # a codex_cli job
    process = RecordingProcess()
    bridge = service_tests.service(spool, req, process)
    bridge.readiness = bridge.readiness.model_copy(update={"provider": "claude_cli"})
    assert asyncio.run(bridge.run_once()) == 1
    assert process.calls == 0
    response = json.loads((spool.path(req.job_id) / "response.json").read_text())
    assert response["failure_code"] == "bridge_model_unavailable"


def test_heartbeat_identity_follows_the_engine(published):
    from infrastructure.codex_bridge.doctor import FileReadiness

    spool, req = published
    bridge = service_tests.service(spool, req)
    bridge.settings.codex_bridge_container_spool = str(spool.root)
    reader = FileReadiness(bridge.settings)
    claude = bridge.readiness.model_copy(update={"provider": "claude_cli"})
    spool.heartbeat(claude.model_dump(mode="json"))
    heartbeat = json.loads((spool.root / ".heartbeat.json").read_text())
    assert (heartbeat["model"], heartbeat["cli_version"]) == (MODEL, "2.1.328")
    readiness = reader.read(req.tenant_id, datetime.now(UTC))
    assert readiness.ready and readiness.provider == "claude_cli"
    # A Claude readiness carried under Codex identity is treated as stale.
    heartbeat["model"] = "gpt-6-luna"
    spool._write(spool.root, ".heartbeat.json", json.dumps(heartbeat).encode())
    assert not reader.read(req.tenant_id, datetime.now(UTC)).ready


@pytest.mark.asyncio
async def test_claude_policy_publishes_a_claude_request_through_the_batch(tmp_path):
    # Regression: round 21 attempt 1 built requests with the Codex defaults, so the
    # contract rejected the Claude-bound consent before any job was published.
    from datetime import timedelta
    from uuid import uuid4

    from agents.vision.codex_service import task_context
    from application.vision_model_batch import VisionModelSession
    from infrastructure.codex_bridge.spool import FileSpool
    from infrastructure.vision.codex_batch import CodexModelBatch
    from test_codex_bridge_contracts import response
    from test_codex_candidate_service import bound_observation, codex_policy
    from test_codex_model_batch import Gateway, wait_authorized

    class ClaudeReadiness:
        def read(self, *_args):
            return CodexBridgeReadiness(provider="claude_cli", configured=True, online=True,
                                        authenticated=True, capabilities_qualified=True)

    bound = bound_observation()
    obs = bound.observation
    bridge_id = uuid4()
    spool = FileSpool(tmp_path / "jobs", bridge_id, obs.tenant_id)
    policy = codex_policy(provider="claude_cli", model=MODEL, codex={
        "dom_transfer_accepted": True, "dom_transfer_provider": "claude_cli"})
    batch = CodexModelBatch(bridge_id=bridge_id, spool=spool, gateway=Gateway(),
                            readiness=ClaudeReadiness(), poll_seconds=0.01)
    task = asyncio.create_task(batch(
        session=VisionModelSession(obs.tenant_id, obs.session_id, "claude_cli", MODEL,
                                   obs.project_id, uuid4(), obs.fencing_token),
        bound=bound, context=task_context("Exercise fixture"), policy=policy, sequence=1,
        deadline=datetime.now(UTC) + timedelta(seconds=20), max_candidates=2, image=None,
        check_policy=lambda: policy,
    ))
    req = await wait_authorized(spool)
    assert (req.provider, req.model, req.consent.dom_transfer_provider) == (
        "claude_cli", MODEL, "claude_cli")
    result = response(req, started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
                      actual_model=MODEL)
    spool.complete(req, result)
    assert await task == result


def test_enforceable_schema_merges_common_candidate_fields_into_every_variant():
    # Round 21 attempt 2: the shared schema is unsatisfiable under strict JSON Schema
    # (variants forbid confidence/expected_outcome that the parent requires), so
    # Claude's valid click batches were rejected and it fell back to stop.
    from agents.vision.codex_service import output_schema

    shared = json.loads(output_schema(3))
    candidate = shared["$defs"]["CodexCandidate"]
    assert "confidence" in candidate["required"]
    assert all("confidence" not in v["properties"] and v["additionalProperties"] is False
               for v in candidate["anyOf"])  # the contradiction being repaired
    fixed = enforceable_schema(output_schema(3))["$defs"]["CodexCandidate"]
    assert set(fixed) == {"anyOf"}
    assert len(fixed["anyOf"]) == len(candidate["anyOf"])
    for variant, original in zip(fixed["anyOf"], candidate["anyOf"], strict=True):
        assert variant["additionalProperties"] is False and variant["type"] == "object"
        assert {"confidence", "expected_outcome"} <= set(variant["required"])
        assert variant["properties"]["kind"] == original["properties"]["kind"]
        assert variant["properties"]["confidence"] == candidate["properties"]["confidence"]
    # Top-level envelope and other result variants are untouched.
    assert enforceable_schema(output_schema(3))["required"] == ["result"]


def test_command_sends_the_enforceable_schema_not_the_prompt_schema():
    from agents.vision.codex_service import output_schema

    schema = output_schema(3)
    argv = claude_command("/usr/local/bin/claude", claude_request(), schema)
    assert json.loads(argv[argv.index("--json-schema") + 1]) == enforceable_schema(schema)


def test_reader_counts_structured_output_rejections():
    reader = ClaudeEventReader()
    reader.event(line(INIT))
    reader.event(line(assistant({"type": "tool_use", "id": "t1", "name": "StructuredOutput"})))
    reader.event(line({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": True}]}}))
    assert reader.schema_rejections == 1
