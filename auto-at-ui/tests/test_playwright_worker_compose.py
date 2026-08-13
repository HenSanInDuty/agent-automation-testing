"""Compose-backed checks for the pinned Playwright execution adapter.

These tests deliberately use the control-plane container as the caller.  That
exercises the same Docker-network boundary used by the local dispatcher while
keeping the browser target deterministic and local.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
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


def compose_command(*arguments: str, input: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        input=input,
        text=True,
        timeout=120,
    )


def csrf_headers(client: httpx.Client, **headers: str) -> dict[str, str]:
    csrf = client.cookies.get("auto_at_csrf")
    assert csrf is not None
    return {"X-CSRF-Token": csrf, **headers}


def wait_for_terminal_run(
    client: httpx.Client, run_id: str, expected_status: str
) -> dict[str, Any]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"passed", "failed", "errored", "cancelled"}:
            assert run["status"] == expected_status
            return run
        time.sleep(1)
    raise AssertionError(f"run {run_id} did not reach {expected_status}")


def seed_governed_review_records(
    tenant_id: str, project_id: str, failed_run_id: str, correlation_id: str
) -> tuple[str, str]:
    """Seed deterministic agent outputs; the review decisions remain public API calls."""
    request_id, draft_id, proposal_id = uuid4(), uuid4(), uuid4()
    source = "import { test } from '@playwright/test';\ntest('health', async () => {});\n"
    script = f"""\
import hashlib
from datetime import UTC, datetime
from uuid import UUID

from config import get_settings
from infrastructure.persistence.models import (
    AgentProposalModel,
    GeneratedTestDraftModel,
    GenerationRequestModel,
)
from infrastructure.persistence.session import create_session_factory, transactional_session

tenant_id = {tenant_id!r}
project_id = UUID({project_id!r})
failed_run_id = UUID({failed_run_id!r})
correlation_id = UUID({correlation_id!r})
request_id = UUID({str(request_id)!r})
draft_id = UUID({str(draft_id)!r})
proposal_id = UUID({str(proposal_id)!r})
source = {source!r}
now = datetime.now(UTC)
with transactional_session(create_session_factory(get_settings())) as session:
    session.add(GenerationRequestModel(
        id=request_id, tenant_id=tenant_id, project_id=project_id,
        correlation_id=correlation_id, target_url="http://control-plane:7000/healthz",
        redacted_request="Check the health response.",
        request_hash=hashlib.sha256(b"Check the health response.").hexdigest(),
        state="completed", failure_reason=None, idempotency_key=f"compose-{{request_id}}",
    ))
    session.flush()
    session.add(GeneratedTestDraftModel(
        id=draft_id, tenant_id=tenant_id, planning_request_id=request_id,
        correlation_id=correlation_id, state="pending_review", title="Health check draft",
        playwright_test_source=source, source_hash=hashlib.sha256(source.encode()).hexdigest(),
        assumptions=["The health endpoint is reachable."],
        stop_conditions=["Do not use credentials."],
        provenance={{"provider": "fixture", "model": "deterministic"}},
        linked_test_case_id=None, linked_run_id=None,
    ))
    session.add(AgentProposalModel(
        id=proposal_id, tenant_id=tenant_id, run_id=failed_run_id,
        correlation_id=correlation_id, kind="healing", proposal_version=1,
        summary="Inspect the failed expected-text assertion.",
        proposal={{"evidence": "deterministic compose failure"}}, created_at=now,
    ))
"""
    compose_command("exec", "-T", "control-plane", "uv", "run", "--no-sync", "python", "-c", script)
    return str(draft_id), str(proposal_id)


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
        "screenshot",
        "step-history",
        "trace",
        "video",
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


def test_compose_dashboard_session_workflow_and_governed_review() -> None:
    """Exercise the dashboard's authenticated core workflow without dev identity headers."""
    suffix = uuid4().hex
    tenant_id = f"compose-dashboard-{suffix}"
    admin_email = f"admin-{suffix}@example.test"
    contributor_email = f"contributor-{suffix}@example.test"
    admin_password = "ComposeAdminPass123"
    compose_command(
        "exec",
        "-T",
        "control-plane",
        "uv",
        "run",
        "--no-sync",
        "python",
        "apps/control-plane/cli.py",
        "bootstrap-admin",
        "--tenant",
        tenant_id,
        "--email",
        admin_email,
        "--temporary-password",
        admin_password,
    )

    with httpx.Client(base_url="http://127.0.0.1:7000", timeout=20) as admin:
        login = admin.post(
            "/api/v1/auth/login",
            json={
                "tenant_id": tenant_id,
                "email": admin_email,
                "password": admin_password,
            },
        )
        assert login.status_code == 200, login.text
        provision = admin.post(
            "/api/v1/admin/users",
            headers=csrf_headers(admin),
            json={
                "email": contributor_email,
                "role": "contributor",
            },
        )
        assert provision.status_code == 201, provision.text
        contributor_password = provision.json()["temporary_password"]
        project = admin.post(
            "/api/v1/projects",
            headers=csrf_headers(admin),
            json={
                "name": "Compose dashboard acceptance",
                "default_target": "web_ui",
            },
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]
        test_case_id = f"compose-dashboard-{suffix}"
        test_case = admin.post(
            f"/api/v1/projects/{project_id}/tests",
            headers=csrf_headers(admin),
            json={
                "id": test_case_id,
                "name": "Compose dashboard test",
                "target_type": "web_ui",
                "revision": "a" * 40,
                "specification": {},
            },
        )
        assert test_case.status_code == 201, test_case.text

        with httpx.Client(base_url="http://127.0.0.1:7000", timeout=20) as contributor:
            login = contributor.post(
                "/api/v1/auth/login",
                json={
                    "tenant_id": tenant_id,
                    "email": contributor_email,
                    "password": contributor_password,
                },
            )
            assert login.status_code == 200, login.text
            changed = contributor.post(
                "/api/v1/auth/change-password",
                headers=csrf_headers(contributor),
                json={
                    "current_password": contributor_password,
                    "new_password": "ComposeContributorPass123",
                },
            )
            assert changed.status_code == 200, changed.text
            assert contributor.get("/api/v1/projects").json()[0]["id"] == project_id
            assert (
                contributor.get(f"/api/v1/projects/{project_id}/tests").json()[0]["id"]
                == test_case_id
            )

            def create_run(expected_text: str) -> dict[str, Any]:
                response = contributor.post(
                    "/api/v1/runs",
                    headers=csrf_headers(contributor, **{"Idempotency-Key": str(uuid4())}),
                    json={
                        "project_id": project_id,
                        "test_case_id": test_case_id,
                        "target_type": "web_ui",
                        "target_url": "http://control-plane:7000/healthz",
                        "runner_config": {
                            "browser": "chromium",
                            "step_timeout_ms": 1000,
                            "steps": [
                                {"action": "goto", "url": "http://control-plane:7000/healthz"},
                                {"action": "expect_text", "text": expected_text},
                            ],
                        },
                        "artifact_policy": {
                            "trace_on_failure": True,
                            "video_on_failure": True,
                            "screenshot_on_failure": True,
                            "retain_days": 30,
                        },
                    },
                )
                assert response.status_code == 201, response.text
                return response.json()

            passed_run = create_run("ok")
            wait_for_terminal_run(contributor, passed_run["id"], "passed")
            timeline = contributor.get(f"/api/v1/activities?run_id={passed_run['id']}")
            assert timeline.status_code == 200 and timeline.json()
            evidence = contributor.get(f"/api/v1/runs/{passed_run['id']}/artifacts")
            assert evidence.status_code == 200 and evidence.json()
            artifact_id = evidence.json()[0]["id"]
            assert (
                contributor.get(
                    f"/api/v1/runs/{passed_run['id']}/artifacts/{artifact_id}"
                ).status_code
                == 200
            )

            failed_run = create_run("deliberately absent")
            wait_for_terminal_run(contributor, failed_run["id"], "failed")
            draft_id, proposal_id = seed_governed_review_records(
                tenant_id, project_id, failed_run["id"], failed_run["correlation_id"]
            )
            drafts = contributor.get("/api/v1/test-generations/drafts?state=pending_review")
            assert drafts.status_code == 200
            assert any(item["id"] == draft_id for item in drafts.json()["items"])
            decision = contributor.post(
                f"/api/v1/test-generations/drafts/{draft_id}/decision",
                headers=csrf_headers(contributor),
                json={"approved": False, "reason": "Compose review rejected this fixture."},
            )
            assert decision.status_code == 200, decision.text
            assert decision.json()["state"] == "rejected"

        proposals = admin.get("/api/v1/proposals")
        assert proposals.status_code == 200
        assert any(item["id"] == proposal_id for item in proposals.json()["items"])
