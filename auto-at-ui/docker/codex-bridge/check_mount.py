"""Check Docker Desktop publication, response, acknowledgement and consumer locking."""

import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

repository = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(repository / path) for path in (
    "apps/control-plane", "packages/contracts/src", "tests",
)]

from infrastructure.codex_bridge.spool import FileSpool  # noqa: E402
from test_codex_bridge_spool import job  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix="auto-at-codex-mount-") as temporary:
        req, dom, schema = job()
        spool = FileSpool(Path(temporary) / "jobs", req.bridge_id, req.tenant_id)
        spool.publish(req, dom, schema)
        spool.authorize(req, datetime.now(UTC) + timedelta(seconds=10))
        base = [
            "docker", "run", "--rm", "--init", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--read-only",
            "--mount", f"type=bind,source={spool.root},target=/codex-jobs",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m", "--entrypoint", "uv",
        ]
        invoke = [
            "auto-at-codex-bridge:0.164.0", "run", "--project", "/app", "--no-sync", "python",
            "/app/tests/fixtures/codex_bridge_mount_probe.py",
        ]
        for mode in ("consume", "reconcile"):
            subprocess.run([*base, *invoke, mode, str(req.bridge_id)], check=True, timeout=20)
            if mode == "consume":
                assert spool.result(req).output.reason == "complete"
                spool.acknowledge(req)
        name = "auto-at-codex-lock-" + uuid4().hex[:12]
        subprocess.run(
            [*base, "--detach", "--name", name, *invoke, "lock", str(req.bridge_id)],
            check=True, capture_output=True, timeout=20,
        )
        try:
            deadline = time.monotonic() + 10
            while not (spool.root / ".lock-held").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("lock-holder did not start")
                time.sleep(0.1)
            subprocess.run(
                [*base, *invoke, "contend", str(req.bridge_id)], check=True, timeout=20,
            )
        finally:
            subprocess.run(["docker", "stop", "--time", "1", name],
                           check=True, capture_output=True, timeout=15)
        print("publication, response, acknowledgement, cleanup and cross-container lock: passed")


if __name__ == "__main__":
    main()
