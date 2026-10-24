"""Deterministic subprocess fixture; never imports or launches real Codex."""

import json
import subprocess
import sys
import time
from pathlib import Path

mode = sys.argv[1]
sys.stdin.buffer.read()
if mode == "startup_warning":
    print(json.dumps({"type": "item.completed", "item": {"type": "error", "message": (
        "Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; "
        "enable `features.code_mode_host` and install `codex-code-mode-host`."
    )}}))
    print(json.dumps({"type": "turn.started"}))
if mode in {"dom_branches", "image_branches", "unknown_element"}:
    request = json.loads(Path("request.json").read_text())
    observation = json.loads(Path("dom.json").read_text())
    if mode == "image_branches" and request["stage"] == "dom":
        output = {"outcome": "need_screenshot", "reason": "visual_target"}
    else:
        elements = [e for e in observation["elements"] if e["name"] in {"Branch A", "Branch B"}]
        output = {
            "outcome": "candidates",
            "candidates": [
                {
                    "kind": "click",
                    "element_id": (
                        "e_ffffffffffffffffffffffffffffffff"
                        if mode == "unknown_element"
                        else e["element_id"]
                    ),
                    "confidence": 0.9,
                    "expected_outcome": "Open synthetic branch",
                }
                for e in elements
            ],
        }
    Path("raw-output.json").write_text(json.dumps({"result": output}))
    print(json.dumps({"type": "thread.started", "model": "gpt-6-luna"}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 2, "output_tokens": 3}}))
    raise SystemExit(0)
if mode == "child":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    Path("child.pid").write_text(str(child.pid))
if mode in {"hang", "child"}:
    time.sleep(60)
if mode == "overflow":
    print("x" * 70_000, flush=True)
    time.sleep(60)
if mode == "stderr_overflow":
    sys.stderr.write("x" * (2 * 1024 * 1024 + 1))
    sys.stderr.flush()
    time.sleep(60)
if mode == "partial":
    sys.stdout.write('{"type":')
    raise SystemExit(0)
if mode == "tool":
    print(json.dumps({"type": "item.started", "item": {"type": "command_execution"}}), flush=True)
    time.sleep(60)
if mode == "wrong_model":
    print(json.dumps({"type": "thread.started", "model": "other"}))
if mode == "malformed":
    Path("raw-output.json").write_text("not JSON")
elif mode == "fenced_json":
    Path("raw-output.json").write_text('```json\n{"outcome":"stop","reason":"complete"}\n```')
elif mode == "extra_fields":
    Path("raw-output.json").write_text(
        '{"outcome":"stop","reason":"complete","execute_script":"forbidden"}'
    )
else:
    Path("raw-output.json").write_text('{"outcome":"stop","reason":"complete"}')
print(
    json.dumps(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 2,
                "output_tokens": 3,
            },
        }
    )
)
raise SystemExit(1 if mode == "nonzero" else 0)
