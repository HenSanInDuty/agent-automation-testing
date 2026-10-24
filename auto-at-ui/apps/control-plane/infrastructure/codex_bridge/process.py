"""Fixed Linux Codex invocation, bounded untrusted streams and process-group ownership."""

import asyncio
import json
import os
import signal
from collections.abc import Callable
from pathlib import Path

from auto_at.contracts.codex_bridge import CodexBridgeRequest, CodexUsage, parse_codex_output
from domain.codex_bridge import CLI_VERSION as CLI_VERSION
from domain.codex_bridge import BridgeProcessResult
from pydantic import ValidationError

from infrastructure.codex_bridge.catalogue import CATALOGUE_PATH, INSTRUCTIONS_PATH
from infrastructure.codex_bridge.spool import _plain

# Qualification must inspect both top-level tools and input.additional_tools.
# 0.163.0 still advertises Code Mode tools with its host disabled and omits
# rejected custom calls from JSONL. Do not qualify it from feature flags alone.
# 0.164.0 qualifies only with the immutable catalogue and fixed arguments below.
TOOL_ISOLATION_QUALIFIED_VERSIONS: frozenset[str] = frozenset({"0.164.0"})
# Historical 0.163.0 emits this before turn.started even with code_mode=false.
# It describes the intentionally disabled tool host, not a failed provider turn.
DISABLED_CODE_MODE_WARNING = (
    "Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; "
    "enable `features.code_mode_host` and install `codex-code-mode-host`."
)
DISABLED_FEATURES = (
    "shell_tool", "shell_snapshot", "apps", "plugins", "hooks",
    "multi_agent", "multi_agent_v2", "code_mode", "code_mode_host", "browser_use",
    "computer_use", "image_generation", "view_image", "memories", "skill_search",
    "workspace_dependencies", "remote_plugin", "tool_suggest", "sleep_tool",
    "unbounded_connection_retries", "goals",
)


def restricted_config(directory: Path) -> list[str]:
    # TOML quoted paths use JSON-compatible escaping. No shell interpolation.
    rules = '{":minimal"="read",' + json.dumps(str(directory)) + '="read"}'
    values = [
        'default_permissions="bridge"', f"permissions.bridge.filesystem={rules}",
        "permissions.bridge.network.enabled=false", 'approval_policy="never"',
        'web_search="disabled"', "project_doc_max_bytes=0",
        'cli_auth_credentials_store="file"', "analytics.enabled=false",
        'otel.metrics_exporter="none"', 'model_reasoning_effort="low"',
        'service_tier="default"', "agents.enabled=false",
        "tools.experimental_request_user_input.enabled=false",
        "model_catalog_json=" + json.dumps(CATALOGUE_PATH.as_posix()),
    ]
    values.extend(f"features.{feature}=false" for feature in DISABLED_FEATURES)
    return [part for value in values for part in ("-c", value)]


def command(executable: str, directory: Path, request: CodexBridgeRequest) -> list[str]:
    args = [
        executable, *restricted_config(directory),
        "-c", "model_instructions_file=" + json.dumps(INSTRUCTIONS_PATH.as_posix()),
        # User-authorized container mode. Tool availability stays disabled;
        # doctor verifies the outer container because --yolo bypasses CLI sandboxing.
        "exec", "--yolo", "--ignore-user-config",
        "--ignore-rules", "--strict-config", "--skip-git-repo-check", "--ephemeral",
        "--model", request.model, "--json", "--color", "never", "--cd", str(directory),
        "--output-last-message", str(directory / "raw-output.json"),
    ]
    if request.stage == "image":
        args.extend(["--image", str(directory / "screenshot.png")])
    return [*args, "-"]


class ProcessRejected(Exception):
    def __init__(self, code: str):
        self.code = code


class EventReader:
    def __init__(self):
        self.total = 0
        self.completed = False
        self.turn_started = False
        self.usage = None
        self.actual_model = None

    async def drain(self, stream, *, events: bool):
        pending = b""
        while chunk := await stream.read(8192):
            self.total += len(chunk)
            if self.total > 2 * 1024 * 1024:
                raise ProcessRejected("bridge_output_limit")
            if not events:
                continue  # stderr is bounded and discarded, never stored or logged.
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                self.event(line)
            if len(pending) > 65_536:
                raise ProcessRejected("bridge_output_limit")
        if pending:
            raise ProcessRejected("bridge_malformed_output")

    def event(self, line: bytes):
        if len(line) > 65_536:
            raise ProcessRejected("bridge_output_limit")
        try:
            event = json.loads(line)
            kind = event["type"]
            if kind in {"error", "turn.failed"}:
                raise ProcessRejected("bridge_provider_unavailable")
            if self.completed:
                raise ProcessRejected("bridge_malformed_output")
            if kind in {"item.started", "item.updated", "item.completed"}:
                if event["item"]["type"] == "error":
                    if (kind != "item.completed" or self.turn_started
                            or event["item"].get("message") != DISABLED_CODE_MODE_WARNING):
                        raise ProcessRejected("bridge_provider_unavailable")
                elif event["item"]["type"] not in {"agent_message", "reasoning"}:
                    raise ProcessRejected("bridge_tool_rejected")
            elif kind == "turn.started":
                self.turn_started = True
            elif kind == "turn.completed":
                self.completed = True
                if event.get("usage") is not None:
                    usage = event["usage"]
                    self.usage = CodexUsage.model_validate({
                        key: usage[key] for key in (
                            "input_tokens", "output_tokens", "cached_input_tokens",
                        ) if key in usage
                    })
            elif kind not in {"thread.started", "turn.started"}:
                raise ProcessRejected("bridge_malformed_output")
            if "model" in event:
                if event["model"] != "gpt-6-luna":
                    raise ProcessRejected("bridge_model_unavailable")
                self.actual_model = event["model"]
        except (ValueError, TypeError, KeyError) as exc:
            raise ProcessRejected("bridge_malformed_output") from exc


class CodexProcess:
    def __init__(self, executable: str, *, poll_seconds=1.0, kill_grace_seconds=3.0):
        self.executable = executable
        self.poll_seconds = poll_seconds
        self.kill_grace_seconds = kill_grace_seconds

    async def run(
        self, request: CodexBridgeRequest, directory: Path, prompt: bytes,
        stop_reason: Callable[[], str | None], *, argv: list[str] | None = None,
    ) -> BridgeProcessResult:
        if os.name != "posix":
            return BridgeProcessResult(failure_code="bridge_cli_unsupported")
        if len(prompt) > 131_072:
            return BridgeProcessResult(failure_code="bridge_output_limit")
        if reason := stop_reason():
            return BridgeProcessResult(failure_code=reason)
        raw = directory / "raw-output.json"
        if raw.exists() or raw.is_symlink():
            return BridgeProcessResult(failure_code="bridge_interrupted")
        # No application/cloud secrets are inherited. The only credential is the
        # dedicated read-only auth-file mount in this private container home.
        environment = {
            "HOME": "/bridge-home", "CODEX_HOME": "/bridge-home/.codex",
            "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "TMPDIR": "/tmp",
        }
        process = None
        tasks = []
        reader = EventReader()
        try:
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                *(argv if argv is not None else command(self.executable, directory, request)),
                cwd=directory, env=environment, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            ))
            try:
                process = await asyncio.shield(spawn)
            except asyncio.CancelledError:
                # Do not lose ownership if shutdown arrives during process creation.
                process = await spawn
                raise

            async def send():
                process.stdin.write(prompt)
                await process.stdin.drain()
                process.stdin.close()
                await process.stdin.wait_closed()

            tasks = [
                asyncio.create_task(reader.drain(process.stdout, events=True)),
                asyncio.create_task(reader.drain(process.stderr, events=False)),
                asyncio.create_task(send()), asyncio.create_task(process.wait()),
            ]
            while not all(task.done() for task in tasks):
                if reason := stop_reason():
                    raise ProcessRejected(reason)
                if raw.exists():
                    _plain(raw)
                    if raw.stat().st_size > request.max_output_bytes:
                        raise ProcessRejected("bridge_output_limit")
                for task in tasks:
                    if task.done() and not task.cancelled() and task.exception():
                        raise task.exception()
                await asyncio.sleep(min(self.poll_seconds, 0.1))
            await asyncio.gather(*tasks)
            if reason := stop_reason():
                raise ProcessRejected(reason)
            if process.returncode != 0:
                raise ProcessRejected("bridge_provider_unavailable")
            if not reader.completed:
                raise ProcessRejected("bridge_malformed_output")
            _plain(raw)
            with raw.open("rb") as result_file:
                data = result_file.read(request.max_output_bytes + 1)
            if len(data) > request.max_output_bytes:
                raise ProcessRejected("bridge_output_limit")
            output = parse_codex_output(data)
            return BridgeProcessResult(
                output=output, actual_model=reader.actual_model, usage=reader.usage,
            )
        except ProcessRejected as exc:
            return BridgeProcessResult(failure_code=exc.code)
        except (ValueError, ValidationError, BrokenPipeError, ConnectionResetError):
            return BridgeProcessResult(failure_code="bridge_malformed_output")
        except OSError:
            return BridgeProcessResult(failure_code="bridge_io_error")
        finally:
            if process is not None:
                # Kill the group even after the leader exits: descendants may own pipes.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                await asyncio.sleep(min(self.kill_grace_seconds, 0.1))
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if raw.exists() and not raw.is_symlink():
                _plain(raw)
                raw.unlink()
