"""Explicitly run the one-call synthetic DOM canary; never enables a tenant."""

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
IMAGE = "auto-at-codex-canary:0.164.0"


def canary_args(name: str, auth: Path) -> list[str]:
    return [
        "docker", "run", "--name", name, "--init", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--security-opt",
        f"seccomp={ROOT / 'docker/codex-bridge/seccomp.json'}",
        "--network", "bridge", "--pids-limit", "512", "--memory", "2g", "--cpus", "2",
        "--shm-size", "256m", "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
        "--tmpfs", "/bridge-home/.codex:rw,nosuid,nodev,uid=1001,gid=1001,mode=700,size=32m",
        "--mount", f"type=bind,source={auth},target=/bridge-home/.codex/auth.json,readonly",
        IMAGE, "--confirm-live-dom",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-dom", action="store_true", required=True)
    parser.add_argument("--auth-file", required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "codex_container", ROOT / "docker/codex-bridge/container.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    auth = module.plain_absolute(args.auth_file)
    if auth.name != "auth.json":
        parser.error("mount only the existing Codex auth.json file")
    suffix = uuid4().hex[:12]
    name = f"auto-at-codex-canary-{suffix}"
    try:
        try:
            result = subprocess.run(
                canary_args(name, auth), cwd=ROOT, timeout=180, capture_output=True, text=True,
            )
            exit_code = result.returncode
            # The entrypoint emits only this safe report. Never echo CLI/container stderr.
            summary = json.loads(result.stdout.strip().splitlines()[-1])
            if summary.get("classification") != "synthetic_live_dom":
                raise ValueError("unexpected canary report")
        except subprocess.TimeoutExpired:
            summary = {"status": "blocked", "failure_code": "canary_container_timeout"}
            exit_code = 1
        except (ValueError, IndexError):
            summary = {"status": "blocked", "failure_code": "canary_report_unavailable"}
            exit_code = 1
        output = ROOT / ".pytest-artifacts" / f"codex-live-{suffix}.json"
        output.parent.mkdir(exist_ok=True)
        # A stopped container loses tmpfs; retain only the explicitly safe stdout report.
        output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({"validation_file": str(output), "summary": summary}), flush=True)
        return exit_code
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
