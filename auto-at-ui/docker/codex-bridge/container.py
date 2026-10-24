"""Launch only the dedicated bridge image, with explicit scope and credential paths."""

import argparse
import subprocess
from pathlib import Path
from uuid import UUID

IMAGE = "auto-at-codex-bridge:0.164.0"


def plain_absolute(value: str, *, directory=False) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or "," in str(path):
        raise ValueError("mount path must be absolute")
    for part in (path, *path.parents):
        info = part.lstat()
        if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("mount path cannot contain a link or reparse point")
    if directory != path.is_dir() or (not directory and not path.is_file()):
        raise ValueError("mount source has the wrong type")
    return path.resolve(strict=True)


def build_args(mode: str, auth: Path, *, spool=None, bridge_id=None, tenant=None):
    args = [
        "docker", "run", "--rm", "--init", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--security-opt",
        f"seccomp={Path(__file__).with_name('seccomp.json').resolve()}",
        "--read-only", "--pids-limit", "128", "--memory", "512m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
        "--tmpfs", "/bridge-home/.codex:rw,nosuid,nodev,uid=1000,gid=1000,mode=700,size=32m",
        "--mount", f"type=bind,source={auth},target=/bridge-home/.codex/auth.json,readonly",
        "--env", "CODEX_BRIDGE_EXECUTABLE=/usr/local/bin/codex",
    ]
    if mode == "doctor":
        args.extend(["--network", "none"])
    elif mode == "run" and spool and bridge_id and tenant:
        if not tenant.isascii() or not all(c.isalnum() or c in "_-" for c in tenant):
            raise ValueError("invalid tenant identifier")
        args.extend([
            "--name", "auto-at-codex-bridge",
            "--mount", f"type=bind,source={spool},target=/codex-jobs",
            "--env", "CODEX_BRIDGE_ENABLED=true", "--env", f"CODEX_BRIDGE_ID={UUID(bridge_id)}",
            "--env", f"CODEX_BRIDGE_ALLOWED_TENANT={tenant}",
            "--env", "CODEX_BRIDGE_HOST_SPOOL=/codex-jobs",
        ])
    else:
        raise ValueError("run requires an existing private spool, bridge ID and tenant")
    args.extend([
        "--entrypoint", "uv", IMAGE, "run", "--project", "/app", "--no-sync", "python",
        "/app/apps/control-plane/codex_bridge_cli.py", mode,
    ])
    return args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("doctor", "run"))
    parser.add_argument("--auth-file", required=True)
    parser.add_argument("--spool")
    parser.add_argument("--bridge-id")
    parser.add_argument("--tenant")
    args = parser.parse_args()
    auth = plain_absolute(args.auth_file)
    if auth.name != "auth.json":
        parser.error("mount only the existing Codex auth.json file")
    spool = plain_absolute(args.spool, directory=True) if args.spool else None
    repository = Path(__file__).resolve().parents[2]
    if spool and (
        auth.parent.is_relative_to(spool) or spool.is_relative_to(auth.parent)
        or spool.is_relative_to(repository) or repository.is_relative_to(spool)
    ):
        parser.error("spool must be outside the repository and credential storage")
    command = build_args(
        args.mode, auth, spool=spool, bridge_id=args.bridge_id, tenant=args.tenant,
    )
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
