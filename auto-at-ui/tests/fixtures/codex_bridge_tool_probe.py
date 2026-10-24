"""Capture CLI tool declarations against loopback only, without credentials/inference."""

import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import zstandard
from agents.prompts.codex_exploration import INSTRUCTIONS, with_response_schema
from agents.vision.codex_service import output_schema
from auto_at.contracts.codex_bridge import parse_codex_output
from codex_bridge_wire import declared_tool_names
from infrastructure.codex_bridge.process import EventReader, ProcessRejected, command

requests = []
marker = Path("/tmp/auto-at-forbidden-tool-marker")
valid_response = "--valid-response" in sys.argv
custom_call = "--custom-call" in sys.argv


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        data = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "zstd":
            data = zstandard.ZstdDecompressor().decompress(data, max_output_size=1_000_000)
        requests.append(json.loads(data))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if len(requests) == 1 and custom_call:
            patch = f"*** Begin Patch\n*** Add File: {marker}\n+synthetic\n*** End Patch"
            item = {"id": "ct_probe", "type": "custom_tool_call", "call_id": "probe_call",
                    "namespace": "functions", "name": "exec",
                    "input": "text(await tools.apply_patch(" + json.dumps(patch) + "));"}
        elif len(requests) == 1 and not valid_response:
            item = {"id": "fc_probe", "type": "function_call", "call_id": "probe_call",
                    "name": "exec_command", "arguments": json.dumps({
                        "cmd": f"touch {marker}",
                    })}
        else:
            item = {"id": "msg_probe", "type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps({
                        "result": {"outcome": "stop", "reason": "complete"},
                    })}]}
        response = {"id": "resp_probe", "model": "gpt-6-luna", "status": "completed",
                    "output": [item], "usage": {
                        "input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                    }}
        events = [
            {"type": "response.created", "response": {"id": "resp_probe"}},
            {"type": "response.output_item.done", "output_index": 0, "item": item},
            {"type": "response.completed", "response": response},
        ]
        for event in events:
            self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
        self.wfile.flush()


server = HTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with tempfile.TemporaryDirectory(prefix="codex-protocol-") as temporary:
        directory = Path(temporary)
        (directory / "response.schema.json").write_bytes(output_schema(1))
        invoke = command("/usr/local/bin/codex", directory,
                         SimpleNamespace(model="gpt-6-luna", stage="dom"))
        invoke[1:1] = [
        "-c", 'model_provider="fixture"',
        "-c", 'model_providers.fixture.name="Fixture"',
        "-c", f'model_providers.fixture.base_url="http://127.0.0.1:{server.server_port}/v1"',
        "-c", 'model_providers.fixture.wire_api="responses"',
        "-c", "model_providers.fixture.requires_openai_auth=false",
        "-c", "model_providers.fixture.request_max_retries=0",
        "-c", "model_providers.fixture.stream_max_retries=0",
        ]
        prompt = with_response_schema(b"Synthetic offline fixture.", output_schema(1)).decode()
        process = subprocess.run(invoke, input=prompt,
                                 capture_output=True, text=True, timeout=30)
        completed = False
        if valid_response and (directory / "raw-output.json").is_file():
            reader = EventReader()
            for line in process.stdout.splitlines():
                reader.event(line.encode())
            output = parse_codex_output((directory / "raw-output.json").read_bytes())
            completed = reader.completed and output.outcome == "stop" and process.returncode == 0
finally:
    server.shutdown()
names = sorted({name for request in requests for name in declared_tool_names(request)})
schema_in_prompt_only = bool(requests) and all(
    "format" not in request.get("text", {}) and any(
        item.get("role") == "user" and any(
            '"response_schema":' in content.get("text", "")
            for content in item.get("content", [])
        ) for item in request.get("input", [])
    ) for request in requests
)
yolo_permissions_sent = bool(requests) and all(any(
    "`sandbox_mode` is `danger-full-access`" in content.get("text", "")
    for item in request.get("input", []) for content in item.get("content", [])
) for request in requests)
proposal_instructions_sent = bool(requests) and all(any(
    item.get("role") == "developer" and any(
        content.get("text", "").strip() == INSTRUCTIONS.strip()
        for content in item.get("content", [])
    ) for item in request.get("input", [])
) for request in requests)
custom_outputs = [item for request in requests for item in request.get("input", [])
                  if item.get("type") == "custom_tool_call_output"]
custom_output_seen = bool(custom_outputs)
unsupported_custom_call = any(
    item.get("output") == "unsupported custom tool call: exec" for item in custom_outputs
)
event_reader = EventReader()
events_accepted = False
try:
    for line in process.stdout.splitlines():
        event_reader.event(line.encode())
    events_accepted = event_reader.completed
except ProcessRejected:
    pass
print(json.dumps({"requests": len(requests), "tools": names,
                  "yolo_permissions_sent": yolo_permissions_sent,
                  "schema_in_prompt_only": schema_in_prompt_only,
                  "proposal_instructions_sent": proposal_instructions_sent,
                  "forbidden_tool_executed": marker.exists(),
                  "valid_response_completed": completed,
                  "custom_call_output_seen": custom_output_seen,
                  "custom_call_unsupported": unsupported_custom_call,
                  "custom_call_denied_by_disabled_host": any(
                      item.get("output") == "code-mode host is disabled"
                      for item in custom_outputs),
                  "jsonl_accepted_after_custom_call": custom_output_seen and events_accepted,
                  "tool_isolation_qualified": bool(requests) and not names,
                  "exit_code": process.returncode}))
raise SystemExit(0 if (requests and not names and not marker.exists()
                      and proposal_instructions_sent
                      and yolo_permissions_sent
                      and schema_in_prompt_only
                      and (not custom_call or unsupported_custom_call)
                      and (not valid_response or completed)) else 1)
