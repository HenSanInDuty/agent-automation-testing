"""Synthetic bind-mount consumer; neither credentials nor real Codex are used."""

import asyncio
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from application.codex_bridge import BridgeService
from auto_at.contracts.codex_bridge import CodexBridgeReadiness, CodexStop
from config import Settings
from domain.codex_bridge import BridgeProcessResult
from infrastructure.codex_bridge.spool import FileSpool


class FakeProcess:
    async def run(self, *_args):
        return BridgeProcessResult(output=CodexStop(reason="complete"))


def main():
    mode, bridge_id = sys.argv[1:]
    spool = FileSpool(Path("/codex-jobs"), UUID(bridge_id), "fixture")
    if mode == "lock":
        with spool.lock(consumer=True):
            (spool.root / ".lock-held").write_text("ready")
            time.sleep(30)
    elif mode == "contend":
        try:
            with spool.lock(consumer=True):
                return 1
        except OSError:
            return 0
    elif mode == "reconcile":
        with spool.lock(consumer=True):
            spool.reconcile(datetime.now(UTC))
        assert not spool.jobs()
    elif mode == "consume":
        settings = Settings(
            _env_file=None, codex_bridge_enabled=True, codex_bridge_id=UUID(bridge_id),
            codex_bridge_allowed_tenant="fixture", codex_bridge_host_spool="/codex-jobs",
            codex_bridge_executable="/usr/local/bin/codex",
        )
        service = BridgeService(
            settings, spool, FakeProcess(), lambda *_args: b"synthetic",
            CodexBridgeReadiness(configured=True, online=True, authenticated=True,
                                 capabilities_qualified=True),
        )
        assert asyncio.run(service.run_once()) == 1
    else:
        raise ValueError("invalid probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
