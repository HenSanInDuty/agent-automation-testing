"""Run tests and all descendants in an owned, network-isolated Docker namespace.

No host mounts, provider credentials, application services or real Codex executable.
Builds copy only explicit source directories; pytest arguments follow this script.
"""

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
IMAGE = "auto-at-codex-offline:playwright-1.50.1"


def suite_args(database: str, container: str, pytest_args: list[str]) -> list[str]:
    if any("test_playwright_worker_compose" in arg for arg in pytest_args):
        raise ValueError("the configured-stack workflow is excluded from offline evaluation")
    return [
        "docker", "run", "--name", container, "--init",
        "--network", f"container:{database}", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "512",
        "--memory", "3g", "--shm-size", "512m", IMAGE, *pytest_args,
    ]


def main() -> int:
    suffix = uuid4().hex[:12]
    database, suite = f"auto-at-codex-db-{suffix}", f"auto-at-codex-tests-{suffix}"
    args = suite_args(database, suite, sys.argv[1:])
    subprocess.run([
        "docker", "build", "-t", IMAGE,
        "-f", "benchmark/vision/codex/Dockerfile", ".",
    ], cwd=ROOT, check=True)
    try:
        # A network:none namespace has loopback only. Sharing it lets all test
        # descendants reach this DB and their local browser, never the app or internet.
        subprocess.run([
            "docker", "run", "--detach", "--name", database, "--network", "none",
            "--env", "POSTGRES_PASSWORD=vision-fixture-only", "--tmpfs",
            "/var/lib/postgresql/data:rw,size=512m", "postgres:17-alpine",
            "postgres", "-p", "55437",
        ], check=True, capture_output=True)
        result = subprocess.run(args, cwd=ROOT)
        output = ROOT / ".pytest-artifacts" / f"codex-offline-{suffix}.json"
        output.parent.mkdir(exist_ok=True)
        copied = subprocess.run(
            ["docker", "cp", f"{suite}:/tmp/codex-validation.json", str(output)],
            capture_output=True,
        )
        if copied.returncode == 0:
            summary = json.loads(output.read_text())
            print(json.dumps({"validation_file": str(output), "summary": summary}), flush=True)
        return result.returncode
    finally:
        # Exact UUID names created by this invocation; no volumes or application names.
        for name in (suite, database):
            subprocess.run(["docker", "rm", "--force", name], capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
