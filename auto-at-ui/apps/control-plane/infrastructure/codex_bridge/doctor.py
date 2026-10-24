"""Offline container, version, authentication and fallback sandbox checks; no inference."""

import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path

from auto_at.contracts.codex_bridge import CodexBridgeReadiness
from config import Settings

from infrastructure.codex_bridge.catalogue import validate_catalogue, validate_instructions
from infrastructure.codex_bridge.process import (
    CLI_VERSION,
    DISABLED_FEATURES,
    TOOL_ISOLATION_QUALIFIED_VERSIONS,
    restricted_config,
)


def container_flags_qualified(*, uid: int, root_read_only: bool, status: str) -> bool:
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    try:
        return (uid != 0 and root_read_only and fields.get("NoNewPrivs", "").strip() == "1"
                and int(fields["CapEff"].strip(), 16) == 0
                and fields.get("Seccomp", "").strip() == "2")
    except (KeyError, ValueError):
        return False


def doctor(settings: Settings) -> CodexBridgeReadiness:
    configured = bool(
        settings.codex_bridge_enabled and settings.codex_bridge_id
        and settings.codex_bridge_allowed_tenant and settings.codex_bridge_host_spool
    )
    fail = CodexBridgeReadiness(configured=configured, failure_code="bridge_cli_unsupported")
    # Offline filesystem probes and feature flags cannot certify model tool
    # isolation. The pinned CLI's full wire protocol must also be qualified.
    if CLI_VERSION not in TOOL_ISOLATION_QUALIFIED_VERSIONS:
        return fail
    executable = settings.codex_bridge_executable
    if (os.name != "posix" or not Path("/.dockerenv").is_file()
            or executable != "/usr/local/bin/codex"):
        return fail

    def run(args):
        return subprocess.run(
            [executable, *args], capture_output=True, text=True, timeout=10,
            env={"HOME": "/bridge-home", "CODEX_HOME": "/bridge-home/.codex",
                 "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
        )

    try:
        # --yolo intentionally bypasses the CLI sandbox. The fixed launchers
        # provide this independent boundary; never qualify a normal host process.
        if not container_flags_qualified(
            uid=os.geteuid(), root_read_only=bool(os.statvfs("/").f_flag & os.ST_RDONLY),
            status=Path("/proc/self/status").read_text(),
        ):
            return fail
        version = run(["--version"])
        if version.returncode or version.stdout.strip() != f"codex-cli {CLI_VERSION}":
            return fail
        validate_catalogue(executable)
        validate_instructions()
        help_text = run(["exec", "--help"])
        for flag in ("--ignore-user-config", "--strict-config", "--ephemeral",
                     "--output-last-message", "--json", "--image", "--ignore-rules",
                     "--dangerously-bypass-approvals-and-sandbox"):
            if help_text.returncode or flag not in help_text.stdout:
                return fail
        with tempfile.TemporaryDirectory(prefix="bridge-doctor-") as temporary:
            parent = Path(temporary)
            job = parent / "job"
            job.mkdir()
            (job / "allowed").write_text("synthetic")
            (parent / "denied").write_text("synthetic")
            configuration = restricted_config(job)
            features = run([*configuration, "features", "list"])
            states = {line.split()[0]: line.split()[-1]
                      for line in features.stdout.splitlines() if len(line.split()) >= 3}
            all_disabled = all(states.get(name) == "false" for name in DISABLED_FEATURES)
            if features.returncode or not all_disabled:
                return fail
            # Compatibility probes for the retained fallback profile only.
            # They do not describe the effective permissions of exec --yolo.
            sandbox = [
                *configuration, "sandbox", "--permission-profile", "bridge", "-C", str(job), "--",
            ]
            allowed = run([*sandbox, "/bin/cat", str(job / "allowed")])
            if allowed.returncode or allowed.stdout != "synthetic":
                return fail
            for denied in (parent / "denied", Path("/bridge-home/.codex/auth.json"),
                           Path("/proc/1/root/bridge-home/.codex/auth.json")):
                # Never read real credentials: check readability with test(1), no content output.
                if run([*sandbox, "/usr/bin/test", "-r", str(denied)]).returncode != 1:
                    return fail
            if run([*sandbox, "/usr/bin/touch", str(job / "write")]).returncode == 0:
                return fail
            python_ok = run([*sandbox, "/usr/local/bin/python3", "-c", "print('ready')"])
            if python_ok.returncode or python_ok.stdout.strip() != "ready":
                return fail
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(2)
                port = listener.getsockname()[1]
                probe = f"import socket; socket.create_connection(('127.0.0.1', {port}), 1)"
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
                if run([*sandbox, "/usr/local/bin/python3", "-c", probe]).returncode != 1:
                    return fail
        login = run(["-c", 'cli_auth_credentials_store="file"', "login", "status"])
        authenticated = login.returncode == 0 and "Logged in using ChatGPT" in (
            login.stdout + login.stderr
        )
        return CodexBridgeReadiness(
            configured=configured, online=False, authenticated=authenticated,
            capabilities_qualified=True, model_access="unverified",
            failure_code=None if authenticated else "bridge_login_required",
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return fail


class FileReadiness:
    def __init__(self, settings: Settings):
        self.settings = settings

    def read(self, tenant_id, now):
        from datetime import datetime

        settings = self.settings
        if not settings.codex_bridge_enabled or tenant_id != settings.codex_bridge_allowed_tenant:
            return CodexBridgeReadiness()
        try:
            root = Path(settings.codex_bridge_container_spool)
            from infrastructure.codex_bridge.spool import _plain
            _plain(root, directory=True)
            file = root / ".heartbeat.json"
            _plain(file)
            with file.open("rb") as source:
                data = json.loads(source.read(4097))
            age = (now - datetime.fromisoformat(data["recorded_at"])).total_seconds()
            if (not 0 <= age < settings.codex_bridge_stale_seconds
                    or data["tenant_id"] != tenant_id
                    or data["bridge_id"] != str(settings.codex_bridge_id)
                    or data["model"] != "gpt-6-luna" or data["protocol"] != "v1"
                    or data["cli_version"] != CLI_VERSION):
                raise ValueError("stale heartbeat")
            return CodexBridgeReadiness.model_validate(data["readiness"])
        except (OSError, ValueError, KeyError, TypeError):
            return CodexBridgeReadiness(configured=True, failure_code="bridge_offline")
