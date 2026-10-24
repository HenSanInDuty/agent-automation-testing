"""Bounded stream parsing and Linux process ownership against an offline fake CLI."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest
from infrastructure.codex_bridge.process import (
    DISABLED_CODE_MODE_WARNING,
    CodexProcess,
    EventReader,
    ProcessRejected,
    command,
)
from test_codex_bridge_spool import job


@pytest.mark.parametrize("event,code", [
    (b'{"type":"item.started","item":{"type":"command_execution"}}', "bridge_tool_rejected"),
    (b'{"type":"item.completed","item":{"type":"mcp_tool_call"}}', "bridge_tool_rejected"),
    (b'{"type":"item.completed","item":{"type":"error","message":"private"}}',
     "bridge_provider_unavailable"),
    (b'{"type":"thread.started","model":"wrong"}', "bridge_model_unavailable"),
    (b'[]', "bridge_malformed_output"),
    (b'{"type":"new.unknown.event"}', "bridge_malformed_output"),
    (b"x" * 65_537, "bridge_output_limit"),
], ids=["shell", "mcp", "provider_error", "model", "array", "unknown", "large"])
def test_event_rejections(event, code):
    with pytest.raises(ProcessRejected) as error:
        EventReader().event(event)
    assert error.value.code == code


def test_command_has_fixed_model_sandbox_no_image_or_shell():
    req, _, _ = job()
    args = command("/usr/local/bin/codex", Path("/job"), req)
    assert args[args.index("--model") + 1] == "gpt-6-luna"
    assert "features.shell_tool=false" in args
    assert "--image" not in args
    assert "--output-schema" not in args
    assert "--ignore-user-config" in args and "--ephemeral" in args
    assert args[args.index("exec") + 1] == "--yolo"
    assert 'default_permissions="bridge"' in args
    assert "agents.enabled=false" in args
    assert "features.goals=false" in args
    assert "features.code_mode_host=false" in args
    assert "tools.experimental_request_user_input.enabled=false" in args
    assert 'model_catalog_json="/app/codex-model-catalogue.json"' in args
    assert 'model_instructions_file="/app/codex-proposal-instructions.txt"' in args


def test_only_exact_disabled_host_startup_warning_is_nonfatal():
    reader = EventReader()
    warning = {"type": "item.completed", "item": {
        "type": "error", "message": DISABLED_CODE_MODE_WARNING,
    }}
    encoded = json.dumps(warning).encode()
    reader.event(encoded)
    assert not reader.completed
    altered = json.dumps(warning).replace("disabled.", "enabled.").encode()
    with pytest.raises(ProcessRejected, match="bridge_provider_unavailable"):
        reader.event(altered)
    reader.event(b'{"type":"turn.started"}')
    with pytest.raises(ProcessRejected, match="bridge_provider_unavailable"):
        reader.event(encoded)
    reader.event(b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}')
    assert reader.completed


@pytest.mark.skipif(os.name != "posix", reason="bridge process runs in the Linux container")
@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected", [
    ("success", None), ("startup_warning", None), ("nonzero", "bridge_provider_unavailable"),
    ("malformed", "bridge_malformed_output"), ("partial", "bridge_malformed_output"),
    ("fenced_json", "bridge_malformed_output"), ("extra_fields", "bridge_malformed_output"),
    ("tool", "bridge_tool_rejected"), ("overflow", "bridge_output_limit"),
    ("stderr_overflow", "bridge_output_limit"), ("wrong_model", "bridge_model_unavailable"),
    ("hang", "bridge_cancelled"), ("child", "bridge_cancelled"),
])
async def test_fake_process_lifecycle(tmp_path, mode, expected):
    req, _, _ = job()
    began = time.monotonic()
    def stop():
        return "bridge_cancelled" if time.monotonic() - began > 1 else None
    process = CodexProcess("/must-not-run-real-codex", poll_seconds=0.02)
    result = await process.run(
        req, tmp_path, b"synthetic", stop,
        argv=[sys.executable,
              str(Path(__file__).parent / "fixtures/codex_bridge_fake_cli.py"), mode],
    )
    assert result.failure_code == expected
    assert time.monotonic() - began < 5
    assert not (tmp_path / "raw-output.json").exists()
    if expected is None:
        assert result.output.outcome == "stop"
        assert result.usage.input_tokens == 2
    if mode == "child":
        pid = int((tmp_path / "child.pid").read_text())
        # Docker --init reaps terminated orphan descendants; a zombie cannot execute.
        status = Path(f"/proc/{pid}/status")
        assert not status.exists() or "\nState:\tZ" in status.read_text()


@pytest.mark.skipif(os.name != "posix", reason="bridge process runs in the Linux container")
@pytest.mark.asyncio
async def test_shutdown_during_spawn_retains_process_ownership(tmp_path, monkeypatch):
    req, _, _ = job()
    original = asyncio.create_subprocess_exec
    created = asyncio.Event()
    release = asyncio.Event()
    children = []
    async def delayed(*args, **kwargs):
        process = await original(*args, **kwargs)
        children.append(process)
        created.set()
        await release.wait()
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed)
    process = CodexProcess("/must-not-run-real-codex")
    task = asyncio.create_task(process.run(
        req, tmp_path, b"synthetic", lambda: None,
        argv=[sys.executable, "-c", "import time; time.sleep(60)"],
    ))
    await asyncio.wait_for(created.wait(), timeout=5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None
