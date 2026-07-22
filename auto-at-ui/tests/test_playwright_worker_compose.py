"""Compose-backed checks for the pinned Playwright execution adapter.

These tests deliberately use the control-plane container as the caller.  That
exercises the same Docker-network boundary used by the local dispatcher while
keeping the browser target deterministic and local.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_REQUEST_SCRIPT = """
import json
import sys
import urllib.request

payload = sys.stdin.read().encode()
response = urllib.request.urlopen(
    urllib.request.Request(
        "http://playwright-worker:7100/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
    ),
    timeout=90,
)
print(response.read().decode())
"""


def compose_is_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "compose", "ps", "--status", "running", "--services"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and {"control-plane", "playwright-worker"} <= set(
        result.stdout.split()
    )


@pytest.fixture(scope="module", autouse=True)
def require_compose_worker() -> None:
    if not compose_is_ready():
        pytest.skip("requires running control-plane and playwright-worker Compose services")


def execute_worker(steps: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "contract_version": "v1",
        "run_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "project_id": str(uuid4()),
        "test_case_id": "compose-worker-check",
        "target_type": "web_ui",
        "target_url": "http://control-plane:7000/healthz",
        "revision": "a" * 40,
        "runner_config": {"browser": "chromium", "step_timeout_ms": 1_000, "steps": steps},
        "artifact_policy": {
            "trace_on_failure": True,
            "video_on_failure": True,
            "screenshot_on_failure": True,
            "retain_days": 30,
        },
    }
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "control-plane", "python", "-c", WORKER_REQUEST_SCRIPT],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        input=json.dumps(payload),
        text=True,
        timeout=95,
    )
    return json.loads(result.stdout)


def artifact_kinds(result: dict[str, Any]) -> set[str]:
    return {artifact["kind"] for artifact in result["artifacts"]}


def test_compose_worker_reports_a_deterministic_pass() -> None:
    result = execute_worker(
        [
            {"action": "goto", "url": "http://control-plane:7000/healthz"},
            {"action": "expect_text", "text": "ok"},
        ]
    )

    assert result["status"] == "passed"
    assert artifact_kinds(result) == {
        "accessibility",
        "console-errors",
        "dom-fragment",
        "network-failures",
        "page-url",
        "step-history",
    }


def test_compose_worker_reports_failure_and_evidence() -> None:
    result = execute_worker(
        [
            {"action": "goto", "url": "http://control-plane:7000/healthz"},
            {"action": "expect_text", "text": "deliberately absent"},
        ]
    )

    assert result["status"] == "failed"
    assert {"screenshot", "trace", "video"} <= artifact_kinds(result)
    evidence = result["runner_metadata"]["evidence"]
    assert all(artifact["uri"] in evidence for artifact in result["artifacts"])
