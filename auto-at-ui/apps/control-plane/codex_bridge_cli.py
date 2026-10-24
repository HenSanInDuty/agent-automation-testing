"""Dedicated container entrypoint. Doctor never invokes a model or contacts the DB."""

import argparse
import asyncio
import json
import signal
from pathlib import Path

from agents.prompts.codex_exploration import build_prompt
from application.codex_bridge import BridgeService
from config import Settings
from infrastructure.codex_bridge.doctor import doctor
from infrastructure.codex_bridge.process import CodexProcess
from infrastructure.codex_bridge.spool import FileSpool


async def run(settings, readiness):
    stopped = asyncio.Event()
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, task.cancel)
    spool = FileSpool(
        Path(settings.codex_bridge_container_spool), settings.codex_bridge_id,
        settings.codex_bridge_allowed_tenant, settings.codex_bridge_max_pending,
    )
    service = BridgeService(
        settings, spool, CodexProcess(
            settings.codex_bridge_executable,
            poll_seconds=settings.codex_bridge_cancel_poll_seconds,
            kill_grace_seconds=settings.codex_bridge_kill_grace_seconds,
        ), build_prompt, readiness.model_copy(update={"online": True}),
    )
    try:
        await service.serve(stopped)
    except asyncio.CancelledError:
        stopped.set()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "run"))
    args = parser.parse_args()
    settings = Settings(_env_file=None)
    readiness = doctor(settings)
    print(json.dumps(readiness.model_dump(mode="json")), flush=True)
    if args.command == "doctor":
        return 0 if readiness.capabilities_qualified and readiness.authenticated else 1
    if (not settings.codex_bridge_enabled or not readiness.configured
            or not readiness.capabilities_qualified or not readiness.authenticated):
        return 1
    try:
        asyncio.run(run(settings, readiness))
    except (OSError, ValueError):
        print('{"failure_code":"bridge_io_error"}')
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
