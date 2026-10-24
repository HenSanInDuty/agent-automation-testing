"""Offline container qualification. No real credentials or model invocation."""

import json
import subprocess
import tempfile
from pathlib import Path

IMAGE = "auto-at-codex-bridge:0.164.0"


def qualify(sentinel: Path) -> int:
    docker = [
        "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--read-only", "--pids-limit", "64",
        "--security-opt", f"seccomp={Path(__file__).with_name('seccomp.json').resolve()}",
        "--memory", "256m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
        "--tmpfs", "/bridge-home/.codex:rw,nosuid,nodev,uid=1000,gid=1000,mode=700,size=32m",
        "--mount", (
            f"type=bind,source={sentinel},"
            "target=/bridge-home/.codex/auth.json,readonly"
        ),
        IMAGE,
    ]
    profile = [
        "-c", 'permissions.bridge.filesystem={":minimal"="read","/job"="read"}',
        "-c", "permissions.bridge.network.enabled=false",
        "sandbox", "--permission-profile", "bridge", "--",
    ]
    results = {}
    for name, command in {
        "allowed_read": ["/bin/cat", "/job/allowed.txt"],
        "outside_read": ["/bin/cat", "/outside/sentinel.txt"],
        "credential_read": ["/bin/cat", "/bridge-home/.codex/auth.json"],
        "credential_via_proc": ["/bin/cat", "/proc/1/root/bridge-home/.codex/auth.json"],
        "job_write": ["/bin/touch", "/job/unauthorized.txt"],
    }.items():
        process = subprocess.run(
            [*docker, *profile, *command], capture_output=True, text=True, timeout=45,
        )
        results[name] = {
            "exit_code": process.returncode,
            "allowed_marker": "AUTO_AT_ALLOWED_SYNTHETIC" in process.stdout,
            "denied_marker": "AUTO_AT_DENIED_SYNTHETIC" in process.stdout,
            "diagnostic": process.stderr[-2000:],
        }
    qualified = (
        results["allowed_read"]["exit_code"] == 0
        and results["allowed_read"]["allowed_marker"]
        and all(
            result["exit_code"] != 0 and not result["denied_marker"]
            for name, result in results.items() if name != "allowed_read"
        )
    )
    print(json.dumps({"filesystem_qualified": qualified, "probes": results}, indent=2))
    return 0 if qualified else 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="auto-at-codex-container-") as temporary:
        sentinel = Path(temporary) / "sentinel.txt"
        sentinel.write_text("AUTO_AT_DENIED_SYNTHETIC", encoding="utf-8")
        return qualify(sentinel)


if __name__ == "__main__":
    raise SystemExit(main())
