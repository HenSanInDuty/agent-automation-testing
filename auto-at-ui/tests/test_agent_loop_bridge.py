"""Bridge serves both prompt families: dispatch, spool ceiling, argv/stdin, fake CLI processes."""

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
import test_agent_loop_contracts as contract_tests
import test_claude_bridge as claude_tests
import test_codex_bridge_service as service_tests
import test_codex_model_batch as batch_tests
from agents.prompts.agent_loop import SCHEMA_HEADER, build_prompt
from agents.prompts.codex_exploration import SCHEMA_PROMPT
from agents.vision.codex_service import agent_output_schema, output_schema
from auto_at.contracts.codex_bridge import (
    AGENT_REQUEST_MAX_BYTES,
    AgentLoopContext,
    AgentStep,
    CodexBridgeResponse,
    CodexConsentSnapshot,
    CodexStop,
    canonical_bytes,
    content_hash,
)
from codex_bridge_cli import PROMPT_BUILDERS
from codex_bridge_cli import build_prompt as dispatch_prompt
from domain.codex_bridge import BridgeProcessResult
from infrastructure.codex_bridge.claude_process import (
    ClaudeProcess,
    claude_command,
    claude_input,
    enforceable_schema,
)
from infrastructure.codex_bridge.process import CodexProcess, command
from infrastructure.codex_bridge.spool import REQUEST_MAX_BYTES, FileSpool, SpoolError
from test_codex_bridge_contracts import observation, request, response

harness = batch_tests.harness
IDENTITY = contract_tests.IDENTITY
posix_only = pytest.mark.skipif(
    os.name != "posix", reason="bridge process runs in the Linux container",
)
VIETNAMESE = "ệ"  # three bytes in UTF-8
STEP = {
    "outcome": "agent_step", "evaluation_previous_goal": "Success: menu opened",
    "memory": "clicked 3:1", "next_goal": "click the docs link",
    "actions": [
        {"kind": "click", "ref": "3:2", "text": None, "delta_y": None, "duration_ms": None,
         "expected_outcome": None},
        {"kind": "back", "ref": None, "text": None, "delta_y": None, "duration_ms": None,
         "expected_outcome": "return"},
    ],
}
# A valid v4 output: well formed, but not part of the agent family.
V4_CANDIDATES = {"outcome": "candidates", "candidates": [{
    "kind": "wait", "duration_ms": 100, "confidence": 0.5, "expected_outcome": "pause",
}]}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def agent_context(**changes):
    return {
        "task": "Click every control", "allowed_hosts": ["fixture.test"], "memory": "none yet",
        "history": ["step 1: clicked 3:1"], "snapshot_version": 3,
        "snapshot": "[3:1] button 'Continue'\n[3:2] link 'Docs'", **changes,
    }


def agent_job(*, provider="codex_cli", context=None):
    now = datetime.now(UTC)
    obs = observation(captured_at=now)
    schema = agent_output_schema()
    changes = {}
    if provider == "claude_cli":
        consent = CodexConsentSnapshot(dom_transfer_accepted=True, dom_transfer_provider=provider)
        changes = {"provider": provider, "model": claude_tests.MODEL, "consent": consent,
                   "consent_hash": content_hash(consent)}
    req = request(
        obs, created_at=now, deadline=now + timedelta(seconds=120), prompt_version="agent-loop-v4",
        agent_context=context or agent_context(), inputs={
            "dom_sha256": content_hash(obs), "dom_bytes": len(canonical_bytes(obs)),
            "schema_sha256": sha(schema), "schema_bytes": len(schema),
        }, **changes,
    )
    return req, canonical_bytes(obs), schema


def v4_job(spool_root):
    """The phase-0 sample request, re-timed so the spool accepts it; prompt inputs unchanged."""
    obs, req = contract_tests.sample_request_and_dom()
    schema, now = output_schema(3), datetime.now(UTC)
    req = req.model_copy(update={
        "created_at": now, "deadline": now + timedelta(seconds=120),
        "inputs": req.inputs.model_copy(update={
            "schema_sha256": sha(schema), "schema_bytes": len(schema),
        }),
    })
    spool = FileSpool(spool_root, req.bridge_id, req.tenant_id)
    spool.publish(req, canonical_bytes(obs), schema)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=10))
    return spool, req


@pytest.fixture
def agent_published(tmp_path):
    req, dom, schema = agent_job()
    spool = FileSpool(tmp_path / "jobs", req.bridge_id, req.tenant_id)
    spool.publish(req, dom, schema)
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=10))
    return spool, req


class Capture:
    def __init__(self, output):
        self.output, self.prompts = output, []

    async def run(self, _req, _directory, prompt, _stop):
        self.prompts.append(prompt)
        return BridgeProcessResult(output=self.output)


def host(spool, req, process):
    bridge = service_tests.service(spool, req, process)
    bridge.prompt = dispatch_prompt  # what codex_bridge_cli.run wires in
    return bridge


# Dispatch by prompt_version ------------------------------------------------------------------


def test_cli_registers_exactly_the_two_prompt_families():
    assert set(PROMPT_BUILDERS) == {"codex-dom-v11", "agent-loop-v4"}


def test_dispatch_rejects_a_prompt_version_without_a_builder():
    req = agent_job()[0].model_copy(update={"prompt_version": "agent-loop-v9"})
    with pytest.raises(ValueError, match="unsupported bridge prompt version"):
        dispatch_prompt(req, b"")
    legacy = contract_tests.sample_request_and_dom()[1].model_copy(
        update={"prompt_version": "codex-dom-v10"})
    with pytest.raises(ValueError, match="unsupported bridge prompt version"):
        dispatch_prompt(legacy, b"")


@pytest.mark.asyncio
async def test_agent_job_uses_the_agent_builder_and_does_not_append_a_second_schema(
    agent_published,
):
    spool, req = agent_published
    step = AgentStep.model_validate(STEP)
    process = Capture(step)
    assert await host(spool, req, process).run_once() == 1
    (prompt,) = process.prompts
    dom, _schema = spool.verify_inputs(req)
    assert prompt == build_prompt(req, dom)
    assert SCHEMA_PROMPT.encode() not in prompt and b"response_schema" not in prompt
    assert prompt.decode().count(SCHEMA_HEADER) == 1
    stored = spool.result(req)
    assert stored.output == step and stored.failure_code is None
    assert CodexBridgeResponse.model_validate_json(canonical_bytes(stored)) == stored


@pytest.mark.asyncio
async def test_v4_job_keeps_the_old_builder_wrapper_and_phase_zero_hashes(tmp_path):
    spool, req = v4_job(tmp_path / "jobs")
    process = Capture(CodexStop(reason="complete"))
    assert await host(spool, req, process).run_once() == 1
    (prompt,) = process.prompts
    baseline = IDENTITY["codex_dom_v11_prompt_plus_schema"]
    assert (sha(prompt), len(prompt)) == (baseline["sha256"], baseline["bytes"])
    assert sha(output_schema(3)) == baseline["bridge_schema_sha256"]
    assert b"agent_context" not in (spool.path(req.job_id) / "request.json").read_bytes()
    assert b"agent-loop" not in prompt


# Spool ceiling -------------------------------------------------------------------------------


def test_request_ceiling_constant_comes_from_the_contract():
    assert REQUEST_MAX_BYTES == AGENT_REQUEST_MAX_BYTES == 131_072


def test_vietnamese_24000_char_snapshot_round_trips_through_publish_and_load(tmp_path):
    req, dom, schema = agent_job(context=agent_context(snapshot=VIETNAMESE * 24_000))
    spool = FileSpool(tmp_path / "jobs", req.bridge_id, req.tenant_id)
    spool.publish(req, dom, schema)
    size = (spool.path(req.job_id) / "request.json").stat().st_size
    assert 65_536 < size <= REQUEST_MAX_BYTES  # beyond the old 16 384 read and 65 536 write limits
    loaded = spool.load(req.job_id)
    assert loaded == req and len(loaded.agent_context.snapshot) == 24_000
    spool.authorize(req, datetime.now(UTC) + timedelta(seconds=10))
    assert spool.verify_inputs(req) == (dom, schema)


def test_request_file_over_the_ceiling_is_refused_on_read(agent_published):
    spool, req = agent_published
    (spool.path(req.job_id) / "request.json").write_bytes(b" " * (REQUEST_MAX_BYTES + 1))
    with pytest.raises(SpoolError, match="exceeds limit"):
        spool.load(req.job_id)


def test_dom_and_schema_inputs_keep_their_65536_byte_limit(tmp_path):
    req, dom, schema = agent_job()
    spool = FileSpool(tmp_path / "jobs", req.bridge_id, req.tenant_id)
    for big_dom, big_schema in ((b"x" * 65_537, schema), (dom, b"x" * 65_537)):
        with pytest.raises(SpoolError, match="exceeds limit"):
            spool.publish(req, big_dom, big_schema)
    assert spool.jobs() == []


def test_v4_request_still_publishes_and_loads_unchanged(tmp_path):
    spool, req = v4_job(tmp_path / "jobs")
    assert spool.load(req.job_id) == req
    assert (spool.path(req.job_id) / "request.json").stat().st_size < 16_384


# CodexModelBatch optional parameters ---------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_publishes_an_agent_request_with_its_own_schema_and_context(harness):
    batch, args, spool, gateway, _ready = harness
    context = AgentLoopContext.model_validate(agent_context())
    task = asyncio.create_task(batch(**{
        **args, "context": None, "max_candidates": 10, "prompt_version": "agent-loop-v4",
        "schema_bytes": agent_output_schema(), "agent_context": context,
    }))
    req = await batch_tests.wait_authorized(spool)
    assert (req.prompt_version, req.agent_context, req.context) == ("agent-loop-v4", context, None)
    assert req.stage == "dom" and req.candidate_limit == 10
    assert req.inputs.schema_sha256 == sha(agent_output_schema())
    assert spool.verify_inputs(req)[1] == agent_output_schema()
    result = response(req, started_at=datetime.now(UTC), completed_at=datetime.now(UTC),
                      output=STEP)
    spool.complete(req, result)
    assert await task == result
    assert gateway.events[-1][0] == "finished"


@pytest.mark.asyncio
async def test_batch_defaults_still_publish_the_v4_job(harness):
    batch, args, spool, _gateway, _ready = harness
    task = asyncio.create_task(batch(**args))
    req = await batch_tests.wait_authorized(spool)
    assert req.prompt_version == "codex-dom-v11" and req.agent_context is None
    assert req.inputs.schema_sha256 == sha(output_schema(2))
    assert b"agent_context" not in (spool.path(req.job_id) / "request.json").read_bytes()
    spool.complete(req, response(req, started_at=datetime.now(UTC),
                                 completed_at=datetime.now(UTC)))
    await task


@pytest.mark.asyncio
async def test_batch_rejects_a_stage_that_contradicts_the_image_before_registering(harness):
    batch, args, spool, gateway, _ready = harness
    with pytest.raises(ValueError, match="stage and image"):
        await batch(**{**args, "stage": "image"})
    assert gateway.events == [] and spool.jobs() == []


# argv / stdin ceilings (portable) ------------------------------------------------------------


def big_prompt(provider="codex_cli"):
    req, dom, _schema = agent_job(provider=provider, context=agent_context(
        snapshot=VIETNAMESE * 24_000, task=VIETNAMESE * 4_000, memory=VIETNAMESE * 2_000,
        history=[VIETNAMESE * 600] * 5))
    prompt = build_prompt(req, dom)
    assert 100_000 < len(prompt) < 131_072  # "about 100 KB", under the process ceiling
    return prompt, req


def test_claude_sends_the_agent_schema_on_argv_and_the_whole_prompt_on_stdin(tmp_path):
    prompt, req = big_prompt("claude_cli")
    schema = agent_output_schema()
    argv = claude_command("/usr/local/bin/claude", req, schema)
    assert enforceable_schema(schema) == json.loads(schema)  # flat schema: nothing to merge
    assert json.loads(argv[argv.index("--json-schema") + 1]) == json.loads(schema)
    assert sum(len(part) for part in argv) < 16_384 and prompt.decode() not in " ".join(argv)
    message = json.loads(claude_input(req, tmp_path, prompt))
    assert message["message"]["content"][-1]["text"].encode() == prompt


def test_codex_agent_command_is_the_fixed_v4_command_and_prompt_goes_through_stdin(tmp_path):
    prompt, req = big_prompt()
    argv = command("/usr/local/bin/codex", tmp_path, req)
    assert argv == command("/usr/local/bin/codex", tmp_path, claude_tests.codex_request())
    assert argv[-1] == "-" and max(len(part) for part in argv) < 1_024
    assert len(prompt) > sum(len(part) for part in argv)


# Fake CLI processes: Linux only, like every other process test -------------------------------

CODEX_FAKE = """
import hashlib, json, sys
mode, data = sys.argv[1], sys.stdin.buffer.read()
step = json.loads(sys.argv[2])
step["evaluation_previous_goal"] = "stdin %d %s" % (len(data), hashlib.sha256(data).hexdigest())
if mode == "bad_kind":
    step["actions"][0]["kind"] = "hover"
elif mode == "candidates":
    step = json.loads(sys.argv[3])
elif mode == "v4":
    step = {"outcome": "stop", "reason": "complete"}
open("raw-output.json", "w").write(json.dumps({"result": step}))
print(json.dumps({"type": "thread.started", "model": "gpt-6-luna"}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": 3}}))
"""
CLAUDE_FAKE = """
import hashlib, json, sys
mode, model = sys.argv[1], sys.argv[4]
text = json.loads(sys.stdin.buffer.read())["message"]["content"][-1]["text"].encode()
step = json.loads(sys.argv[2])
step["evaluation_previous_goal"] = "stdin %d %s" % (len(text), hashlib.sha256(text).hexdigest())
if mode == "bad_kind":
    step["actions"][0]["kind"] = "hover"
elif mode == "candidates":
    step = json.loads(sys.argv[3])
elif mode == "v4":
    step = {"outcome": "stop", "reason": "complete"}
for event in (
    {"type": "system", "subtype": "init", "tools": ["StructuredOutput"], "mcp_servers": [],
     "model": model},
    {"type": "assistant", "message": {"model": model, "content": [
        {"type": "tool_use", "id": "t1", "name": "StructuredOutput"}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1"}]}},
    {"type": "result", "subtype": "success", "is_error": False, "stop_reason": "tool_use",
     "structured_output": {"result": step}, "usage": {"input_tokens": 1, "output_tokens": 2}},
):
    print(json.dumps(event), flush=True)
"""


def never_stop():
    return None


async def run_codex(req, directory, prompt, mode):
    argv = [sys.executable, "-c", CODEX_FAKE, mode, json.dumps(STEP), json.dumps(V4_CANDIDATES)]
    return await CodexProcess("/must-not-run-real-codex", poll_seconds=0.02).run(
        req, directory, prompt, never_stop, argv=argv)


async def run_claude(req, directory, prompt, mode):
    (directory / "token").write_text("oat-synthetic")
    (directory / "response.schema.json").write_bytes(agent_output_schema())
    argv = [sys.executable, "-c", CLAUDE_FAKE, mode, json.dumps(STEP),
            json.dumps(V4_CANDIDATES), claude_tests.MODEL]
    return await ClaudeProcess("/must-not-run-real-claude", str(directory / "token"),
                               poll_seconds=0.02).run(
        req, directory, prompt, never_stop, argv=argv)


RUNNERS = {"codex_cli": run_codex, "claude_cli": run_claude}


@posix_only
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["codex_cli", "claude_cli"])
async def test_fake_process_parses_a_100kb_agent_prompt_into_an_agent_step(tmp_path, provider):
    prompt, req = big_prompt(provider)
    result = await RUNNERS[provider](req, tmp_path, prompt, "ok")
    assert result.failure_code is None
    assert isinstance(result.output, AgentStep) and result.output.outcome == "agent_step"
    assert result.output.actions[0].ref == "3:2" and result.output.actions[1].kind == "back"
    # The process received every byte of the ~100 KB prompt, unchanged.
    assert result.output.evaluation_previous_goal == f"stdin {len(prompt)} {sha(prompt)}"


@posix_only
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["codex_cli", "claude_cli"])
@pytest.mark.parametrize("mode", ["bad_kind", "candidates"])
async def test_agent_output_that_breaks_the_agent_schema_is_rejected_like_v4(
    tmp_path, provider, mode,
):
    prompt, req = big_prompt(provider)
    result = await RUNNERS[provider](req, tmp_path, prompt, mode)
    assert (result.failure_code, result.output) == ("bridge_malformed_output", None)


@posix_only
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["codex_cli", "claude_cli"])
async def test_v4_job_keeps_the_v4_parser_and_refuses_agent_output(tmp_path, provider):
    req = (contract_tests.sample_request_and_dom()[1] if provider == "codex_cli"
           else claude_tests.claude_request())
    run = RUNNERS[provider]
    ok = await run(req, tmp_path, b"p", "v4")
    assert ok.failure_code is None and ok.output.outcome == "stop"
    refused = await run(req, tmp_path, b"p", "ok")  # agent_step is not a CodexOutput
    assert (refused.failure_code, refused.output) == ("bridge_malformed_output", None)


@posix_only
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["codex_cli", "claude_cli"])
async def test_prompt_over_the_process_ceiling_fails_closed_without_spawning(tmp_path, provider):
    _prompt, req = big_prompt(provider)
    result = await RUNNERS[provider](req, tmp_path, b"x" * 131_073, "ok")
    assert (result.failure_code, result.output) == ("bridge_output_limit", None)
