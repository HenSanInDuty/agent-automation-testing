"""Synthetic bind-mount consumer; neither credentials nor real Codex are used."""

import asyncio
import os
import sys
import time
from datetime import UTC, datetime, timedelta
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
    root = Path("/codex-jobs")
    # Windows-created files use host ACLs. Linux-created locks carry the
    # explicit UID handoff used by Compose.
    lock = root / ".producer.lock"
    owned = mode in {"publish", "acknowledge"} or lock.exists() and lock.stat().st_uid == 1000
    spool = FileSpool(root, UUID(bridge_id), "fixture", owner_uid=1000 if owned else None)
    if mode == "publish":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from test_codex_bridge_spool import job

        assert os.geteuid() == 0
        req, dom, schema = job()
        req = req.model_copy(update={"bridge_id": UUID(bridge_id)})
        spool.publish(req, dom, schema)
        spool.authorize(req, datetime.now(UTC) + timedelta(seconds=10))
        directory = spool.path(req.job_id)
        assert directory.stat().st_uid == 1000
        assert directory.stat().st_mode & 0o777 == 0o700
        for file in directory.iterdir():
            assert file.stat().st_uid == 1000
            assert file.stat().st_mode & 0o777 == 0o600
    elif mode == "acknowledge":
        assert os.geteuid() == 0
        req = spool.load(spool.jobs()[0])
        assert spool.result(req).output.reason == "complete"
        spool.authorize(req, datetime.now(UTC) + timedelta(seconds=10))
        spool.acknowledge(req)
    elif mode == "lock":
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
        assert os.geteuid() == 1000
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
