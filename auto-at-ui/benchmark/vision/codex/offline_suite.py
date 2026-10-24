"""Container-only pytest entrypoint; the Docker network namespace isolates children."""

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "apps/control-plane"), str(ROOT / "packages/contracts/src")]


def main() -> int:
    if not Path("/.dockerenv").is_file() or shutil.which("codex"):
        raise RuntimeError("offline suite requires its credential-free Docker image")
    if Path("/bridge-home/.codex/auth.json").exists() or (ROOT / ".env").exists():
        raise RuntimeError("offline image must not contain auth or dotenv")
    os.chdir(ROOT)
    from config import Settings, get_settings

    Settings.model_config["env_file"] = None
    os.environ["DATABASE_URL"] = (
        "postgresql+psycopg://postgres:vision-fixture-only@127.0.0.1:55437/postgres"
    )
    get_settings.cache_clear()
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 1})
    deadline = time.monotonic() + 30
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
    engine.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    # Alembic fileConfig must not disable loggers used by the logging regressions.
    for log in logging.Logger.manager.loggerDict.values():
        if isinstance(log, logging.Logger):
            log.disabled = False
    import pytest

    summary = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}

    class Results:
        def pytest_runtest_logreport(self, report):
            if report.skipped:
                summary["skipped"] += 1
            elif report.failed:
                summary["failed" if report.when == "call" else "errors"] += 1
            elif report.when == "call":
                summary["passed"] += 1

    began = time.monotonic()
    result = pytest.main([
        *sys.argv[1:], "--ignore=tests/test_playwright_worker_compose.py",
        "--basetemp=/tmp/codex-pytest", "-p", "no:cacheprovider",
    ], plugins=[Results()])
    summary.update(duration_seconds=round(time.monotonic() - began, 3), exit_code=int(result))
    summary["synthetic_measurements"] = [
        json.loads(path.read_text())
        for path in sorted(Path("/tmp/codex-pytest").glob("**/codex-metrics.json"))
    ]
    Path("/tmp/codex-validation.json").write_text(json.dumps(summary, indent=2))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
