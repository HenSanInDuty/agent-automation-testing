"""Offline container, version, authentication and fallback sandbox checks; no inference."""

import json
import logging
import os
import socket
import subprocess
import tempfile
from pathlib import Path
from time import monotonic, sleep

from auto_at.contracts.codex_bridge import BRIDGE_PROVIDER_MODELS, CodexBridgeReadiness
from config import Settings
from domain.codex_bridge import BRIDGE_CLI_VERSIONS, CLAUDE_CLI_VERSION

from infrastructure.codex_bridge.catalogue import validate_catalogue, validate_instructions
from infrastructure.codex_bridge.claude_process import read_token
from infrastructure.codex_bridge.process import (
    CLI_VERSION,
    DISABLED_FEATURES,
    TOOL_ISOLATION_QUALIFIED_VERSIONS,
    restricted_config,
)


def root_is_overlay(mountinfo: str) -> bool:
    """True when the filesystem mounted at `/` is an overlay, as in an OCI container."""
    overlay = False
    for line in mountinfo.splitlines():
        fields = line.split()
        # id parent major:minor root mount_point options [tags...] - fstype source options
        if len(fields) >= 7 and fields[4] == "/" and "-" in fields[6:]:
            kind = fields[fields.index("-", 6) + 1:][:1]
            overlay = kind == ["overlay"]  # a later mount at `/` covers an earlier one
    return overlay


def inside_container() -> bool:
    """Refuse to run the bridge CLI on a host.

    ADR-046: not every Docker-compatible engine writes `/.dockerenv` (Kiri on WSL2 does not),
    so an overlay root filesystem is accepted as the same evidence. The hardening checks in
    `container_flags_qualified` are separate and unchanged.
    """
    if Path("/.dockerenv").is_file():
        return True
    try:
        return root_is_overlay(Path("/proc/self/mountinfo").read_text())
    except OSError:
        return False


def container_flags_qualified(*, uid: int, root_read_only: bool, status: str) -> bool:
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    try:
        return (uid != 0 and root_read_only and fields.get("NoNewPrivs", "").strip() == "1"
                and int(fields["CapEff"].strip(), 16) == 0
                and fields.get("Seccomp", "").strip() == "2")
    except (KeyError, ValueError):
        return False


def claude_doctor(settings: Settings, configured: bool) -> CodexBridgeReadiness:
    """Offline checks for the `claude -p` engine; no inference, never prints the token."""
    fail = CodexBridgeReadiness(
        provider="claude_cli", configured=configured, failure_code="bridge_cli_unsupported",
    )
    executable = settings.codex_bridge_executable
    if (os.name != "posix" or not inside_container()
            or executable != "/usr/local/bin/claude"):
        return fail
    try:
        if not container_flags_qualified(
            uid=os.geteuid(), root_read_only=bool(os.statvfs("/").f_flag & os.ST_RDONLY),
            status=Path("/proc/self/status").read_text(),
        ):
            return fail
        environment = {"HOME": "/bridge-home", "PATH": "/usr/local/bin:/usr/bin:/bin",
                       "LANG": "C.UTF-8", "DISABLE_AUTOUPDATER": "1"}
        version = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                 timeout=20, env=environment)
        if version.returncode or version.stdout.split()[:1] != [CLAUDE_CLI_VERSION]:
            return fail
        help_text = subprocess.run([executable, "--help"], capture_output=True, text=True,
                                   timeout=20, env=environment)
        for flag in ("--tools", "--strict-mcp-config", "--setting-sources", "--json-schema",
                     "--no-session-persistence", "--disable-slash-commands",
                     "--input-format", "--system-prompt", "--effort"):
            if help_text.returncode or flag not in help_text.stdout:
                return fail
        authenticated = read_token(settings.claude_bridge_token_file) is not None
        return CodexBridgeReadiness(
            provider="claude_cli", configured=configured, online=False,
            authenticated=authenticated, capabilities_qualified=True,
            model_access="unverified",
            failure_code=None if authenticated else "bridge_login_required",
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return fail


def doctor(settings: Settings) -> CodexBridgeReadiness:
    configured = bool(
        settings.codex_bridge_enabled and settings.codex_bridge_id
        and settings.codex_bridge_allowed_tenant and settings.codex_bridge_host_spool
    )
    if settings.codex_bridge_engine == "claude":
        return claude_doctor(settings, configured)
    fail = CodexBridgeReadiness(configured=configured, failure_code="bridge_cli_unsupported")
    # Offline filesystem probes and feature flags cannot certify model tool
    # isolation. The pinned CLI's full wire protocol must also be qualified.
    if CLI_VERSION not in TOOL_ISOLATION_QUALIFIED_VERSIONS:
        return fail
    executable = settings.codex_bridge_executable
    if (os.name != "posix" or not inside_container()
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
        from datetime import datetime, timedelta

        started = monotonic()

        settings = self.settings
        if not settings.codex_bridge_enabled or tenant_id != settings.codex_bridge_allowed_tenant:
            return CodexBridgeReadiness()
        phase, age = "file_read", None
        try:
            root = Path(settings.codex_bridge_container_spool)
            from infrastructure.codex_bridge.spool import SpoolError, _plain
            _plain(root, directory=True)
            file = root / ".heartbeat.json"
            for attempt in range(3):
                try:
                    _plain(file)
                    with file.open("rb") as source:
                        data = json.loads(source.read(4097))
                    break
                except (FileNotFoundError, SpoolError):
                    # Some shared mounts briefly hide the old name during
                    # atomic replacement, and some show the new file with two
                    # links while it is renamed (ADR-046: a live run ended
                    # `bridge_offline` on that). Retry only this read race; a
                    # file that stays unsafe still fails. Never use cached
                    # readiness or relax freshness/identity validation.
                    if attempt == 2:
                        raise
                    sleep(.01)
            # An atomic heartbeat replacement may occur during filesystem I/O.
            # Compare against the end of this read, retaining the caller's clock
            # and the same stale/future limits; do not mistake that race for revocation.
            checked_at = now + timedelta(seconds=monotonic() - started)
            age = (checked_at - datetime.fromisoformat(data["recorded_at"])).total_seconds()
            phase = "freshness"
            if not 0 <= age < settings.codex_bridge_stale_seconds:
                raise ValueError("stale heartbeat")
            phase = "identity"
            readiness = CodexBridgeReadiness.model_validate(data["readiness"])
            if (data["tenant_id"] != tenant_id
                    or data["bridge_id"] != str(settings.codex_bridge_id)
                    or data["model"] != BRIDGE_PROVIDER_MODELS[readiness.provider]
                    or data["protocol"] != "v1"
                    or data["cli_version"] != BRIDGE_CLI_VERSIONS[readiness.provider]):
                raise ValueError("stale heartbeat")
            phase = "readiness"
            return readiness
        except (OSError, ValueError, KeyError, TypeError) as error:
            logging.getLogger(__name__).warning("Bridge heartbeat validation failed.", extra={
                "event": "codex.heartbeat.rejected", "phase": phase,
                "age_seconds": round(age, 6) if age is not None else None,
                "read_duration_ms": round((monotonic() - started) * 1000),
                "error_type": type(error).__name__, "errno": getattr(error, "errno", None),
            })
            return CodexBridgeReadiness(configured=True, failure_code="bridge_offline")
