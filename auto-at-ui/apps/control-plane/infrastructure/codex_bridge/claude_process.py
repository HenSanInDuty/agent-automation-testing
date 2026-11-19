"""Fixed Linux `claude -p` invocation for the local proposal bridge.

Same contract as `CodexProcess`: one bounded, tool-free model turn per job, the
process group is owned and killed, stderr is discarded, and only a schema-valid
proposal leaves this module. Claude Code gets no built-in tools, no MCP servers,
no settings files, no slash commands and no session persistence; the only tool
it may call is the built-in StructuredOutput tool created by `--json-schema`.
"""

import asyncio
import base64
import json
import logging
import os
import signal
from collections.abc import Callable
from pathlib import Path

from agents.prompts.claude_bridge import SYSTEM_PROMPT
from auto_at.contracts.codex_bridge import (
    BRIDGE_PROVIDER_MODELS,
    CodexBridgeRequest,
    CodexUsage,
    parse_codex_output,
)
from domain.codex_bridge import CLAUDE_CLI_VERSION as CLAUDE_CLI_VERSION
from domain.codex_bridge import BridgeProcessResult
from pydantic import ValidationError

CLAUDE_MODEL = BRIDGE_PROVIDER_MODELS["claude_cli"]
CLAUDE_EFFORT = "low"
STRUCTURED_OUTPUT_TOOL = "StructuredOutput"
MAX_EVENT_BYTES = 1024 * 1024
MAX_STREAM_BYTES = 4 * 1024 * 1024
_ALLOWED_BLOCKS = {"text", "thinking", "redacted_thinking"}
_AUTH_STATUSES = {401, 403}


def enforceable_schema(schema: bytes) -> dict:
    """Make the shared response schema satisfiable for a strict JSON Schema validator.

    The shared schema declares common candidate fields (confidence, expected_outcome)
    beside an `anyOf` of per-action variants that each set additionalProperties=false
    without those fields. Codex receives the schema only as prompt text, but
    `--json-schema` enforces it, and under standard semantics no object satisfies
    both. Merge the parent's properties into every variant; the accepted shapes are
    exactly the ones the local Pydantic validator accepts. The prompt text is unchanged.
    """

    def merge(node):
        if isinstance(node, list):
            return [merge(item) for item in node]
        if not isinstance(node, dict):
            return node
        node = {key: merge(value) for key, value in node.items()}
        variants = node.get("anyOf")
        if "properties" in node and isinstance(variants, list) and all(
            isinstance(variant, dict) and "properties" in variant for variant in variants
        ):
            common, required = node.pop("properties"), node.pop("required", [])
            node.pop("additionalProperties", None)
            node.pop("type", None)
            node["anyOf"] = [{
                **variant, "type": "object", "additionalProperties": False,
                "properties": {**common, **variant["properties"]},
                "required": list(dict.fromkeys([*required, *variant.get("required", [])])),
            } for variant in variants]
        return node

    return merge(json.loads(schema))


def claude_command(executable: str, request: CodexBridgeRequest, schema: bytes) -> list[str]:
    """Fixed argv; no shell. Every capability Claude Code could add is switched off."""
    return [
        executable, "-p",
        "--model", request.model, "--effort", CLAUDE_EFFORT,
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--setting-sources", "",
        "--disable-slash-commands", "--no-session-persistence",
        "--system-prompt", SYSTEM_PROMPT,
        "--json-schema", json.dumps(enforceable_schema(schema), separators=(",", ":")),
        "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
    ]


def claude_input(request: CodexBridgeRequest, directory: Path, prompt: bytes) -> bytes:
    content: list[dict] = []
    if request.stage == "image":
        data = (directory / "screenshot.png").read_bytes()
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.b64encode(data).decode("ascii"),
        }})
    content.append({"type": "text", "text": prompt.decode("utf-8")})
    message = {"type": "user", "message": {"role": "user", "content": content}}
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def bridge_environment(token: str) -> dict[str, str]:
    # No application/cloud secrets are inherited. The only credential is the OAuth
    # token read from the dedicated read-only mount; it has no refresh token.
    return {
        "HOME": "/bridge-home", "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8", "TMPDIR": "/tmp",
        "CLAUDE_CODE_OAUTH_TOKEN": token,
        "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }


def read_token(path: str) -> str | None:
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        return None
    token = file.read_text(encoding="utf-8").strip()
    return token if token and len(token) < 4096 and token.isprintable() else None


class ProcessRejected(Exception):
    def __init__(self, code: str):
        self.code = code


class ClaudeEventReader:
    """Validates Claude Code stream-json events; never stores model text."""

    def __init__(self, model: str = CLAUDE_MODEL):
        self.model = model
        self.total = 0
        self.initialized = False
        self.completed = False
        self.output = None
        self.usage = None
        self.actual_model = None
        self.schema_rejections = 0
        self._tool_ids: set[str] = set()

    async def drain(self, stream, *, events: bool):
        pending = b""
        while chunk := await stream.read(65_536):
            self.total += len(chunk)
            if self.total > MAX_STREAM_BYTES:
                raise ProcessRejected("bridge_output_limit")
            if not events:
                continue  # stderr is bounded and discarded, never stored or logged.
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if line.strip():
                    self.event(line)
            if len(pending) > MAX_EVENT_BYTES:
                raise ProcessRejected("bridge_output_limit")
        if pending.strip():
            raise ProcessRejected("bridge_malformed_output")

    def event(self, line: bytes):
        if len(line) > MAX_EVENT_BYTES:
            raise ProcessRejected("bridge_output_limit")
        try:
            event = json.loads(line)
            kind = event["type"]
            if self.completed:
                # Claude Code reports its idle state after the result; nothing else may follow.
                if kind != "system":
                    raise ProcessRejected("bridge_malformed_output")
                return
            if kind == "system":
                if event.get("subtype") == "init":
                    self._init(event)
            elif kind == "assistant":
                self._assistant(event["message"])
            elif kind == "user":
                self._user(event["message"])
            elif kind == "result":
                self._result(event)
            # Other event kinds (rate limits, state changes) carry no model output.
        except ProcessRejected:
            raise
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ProcessRejected("bridge_malformed_output") from exc

    def _init(self, event: dict):
        # Fail closed if the CLI ever exposes a tool or MCP server despite the flags.
        if event.get("tools") != [STRUCTURED_OUTPUT_TOOL] or event.get("mcp_servers"):
            raise ProcessRejected("bridge_tool_rejected")
        if event.get("model") != self.model:
            raise ProcessRejected("bridge_model_unavailable")
        self.initialized = True

    def _assistant(self, message: dict):
        if not self.initialized:
            raise ProcessRejected("bridge_malformed_output")
        if message.get("model") != self.model:
            raise ProcessRejected("bridge_model_unavailable")
        self.actual_model = message["model"]
        for block in message["content"]:
            kind = block["type"]
            if kind == "tool_use":
                if block["name"] != STRUCTURED_OUTPUT_TOOL:
                    raise ProcessRejected("bridge_tool_rejected")
                self._tool_ids.add(block["id"])
            elif kind not in _ALLOWED_BLOCKS:
                raise ProcessRejected("bridge_tool_rejected")

    def _user(self, message: dict):
        content = message["content"]
        if isinstance(content, str):
            raise ProcessRejected("bridge_malformed_output")
        for block in content:
            if block["type"] != "tool_result" or block["tool_use_id"] not in self._tool_ids:
                raise ProcessRejected("bridge_tool_rejected")
            if block.get("is_error"):
                # Claude Code rejected the structured output against --json-schema.
                self.schema_rejections += 1

    def _result(self, event: dict):
        self.completed = True
        usage = event.get("usage") or {}
        if usage:
            cached = int(usage.get("cache_read_input_tokens") or 0)
            self.usage = CodexUsage(
                input_tokens=int(usage.get("input_tokens") or 0) + cached
                + int(usage.get("cache_creation_input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                cached_input_tokens=cached,
            )
        if event.get("is_error") or event.get("subtype") != "success":
            status = event.get("api_error_status")
            if status in _AUTH_STATUSES:
                raise ProcessRejected("bridge_login_required")
            if status == 404:
                raise ProcessRejected("bridge_model_unavailable")
            raise ProcessRejected("bridge_provider_unavailable")
        if event.get("stop_reason") == "refusal":
            raise ProcessRejected("bridge_provider_unavailable")
        if not isinstance(event.get("structured_output"), dict):
            raise ProcessRejected("bridge_malformed_output")
        self.output = event["structured_output"]


class ClaudeProcess:
    def __init__(
        self, executable: str, token_file: str, *, poll_seconds=1.0, kill_grace_seconds=3.0,
    ):
        self.executable = executable
        self.token_file = token_file
        self.poll_seconds = poll_seconds
        self.kill_grace_seconds = kill_grace_seconds

    async def run(
        self, request: CodexBridgeRequest, directory: Path, prompt: bytes,
        stop_reason: Callable[[], str | None], *, argv: list[str] | None = None,
        output_parser: Callable = parse_codex_output,
    ) -> BridgeProcessResult:
        if os.name != "posix":
            return BridgeProcessResult(failure_code="bridge_cli_unsupported")
        if request.provider != "claude_cli" or request.model != CLAUDE_MODEL:
            return BridgeProcessResult(failure_code="bridge_model_unavailable")
        if len(prompt) > 131_072:
            return BridgeProcessResult(failure_code="bridge_output_limit")
        if reason := stop_reason():
            return BridgeProcessResult(failure_code=reason)
        try:
            token = read_token(self.token_file)
            schema = (directory / "response.schema.json").read_bytes()
            stdin = claude_input(request, directory, prompt)
        except (OSError, ValueError):
            return BridgeProcessResult(failure_code="bridge_io_error")
        if token is None:
            return BridgeProcessResult(failure_code="bridge_login_required")
        process = None
        tasks = []
        reader = ClaudeEventReader(request.model)
        phase = "stream"
        try:
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                *(argv if argv is not None else claude_command(self.executable, request, schema)),
                cwd=directory, env=bridge_environment(token), stdin=asyncio.subprocess.PIPE,
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
                process.stdin.write(stdin)
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
                for task in tasks:
                    if task.done() and not task.cancelled() and task.exception():
                        raise task.exception()
                await asyncio.sleep(min(self.poll_seconds, 0.1))
            await asyncio.gather(*tasks)
            if reason := stop_reason():
                raise ProcessRejected(reason)
            if not reader.completed:
                raise ProcessRejected("bridge_malformed_output")
            if process.returncode != 0:
                raise ProcessRejected("bridge_provider_unavailable")
            phase = "output"
            data = json.dumps(reader.output, separators=(",", ":")).encode()
            if len(data) > request.max_output_bytes:
                raise ProcessRejected("bridge_output_limit")
            output = output_parser(data)
            logging.getLogger(__name__).info("Claude proposal: %s", json.dumps({
                "job_id": str(request.job_id), "stage": request.stage,
                "outcome": output.outcome, "reason": getattr(output, "reason", None),
                "candidates": len(getattr(output, "candidates", ()) or ()),
                "schema_rejections": reader.schema_rejections,
            }))
            return BridgeProcessResult(
                output=output, actual_model=reader.actual_model, usage=reader.usage,
            )
        except ProcessRejected as exc:
            logging.getLogger(__name__).warning("Claude rejection: %s", json.dumps({
                "job_id": str(request.job_id), "phase": phase, "code": exc.code,
                "schema_rejections": reader.schema_rejections,
            }))
            return BridgeProcessResult(failure_code=exc.code, usage=reader.usage)
        except (ValueError, ValidationError, BrokenPipeError, ConnectionResetError) as exc:
            # Keep only library error categories, never model output or exception text.
            logging.getLogger(__name__).warning("Claude invalid response: %s", json.dumps({
                "job_id": str(request.job_id), "phase": phase,
                "error_type": type(exc).__name__,
            }))
            return BridgeProcessResult(failure_code="bridge_malformed_output", usage=reader.usage)
        except OSError:
            return BridgeProcessResult(failure_code="bridge_io_error")
        finally:
            if process is not None:
                # Kill the group even after the leader exits: descendants may own pipes.
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        pass
                    if sig == signal.SIGTERM:
                        await asyncio.sleep(min(self.kill_grace_seconds, 0.1))
                await process.wait()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
