"""Run fixture tests with no dotenv, inherited app config or external Python sockets.

Requires an owned PostgreSQL fixture on 127.0.0.1:55437. Never uses the app DB.
Run from repository root with uv; additional arguments are passed to pytest.
"""

import ipaddress
import os
import socket
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/control-plane"))
sys.path.insert(0, str(ROOT / "packages/contracts/src"))

from config import Settings, get_settings  # noqa: E402


def main() -> int:
    os.chdir(ROOT)
    # Importing Settings does not instantiate it or read .env.
    Settings.model_config["env_file"] = None
    names = {name.upper() for name in Settings.model_fields}
    for field in Settings.model_fields.values():
        alias = field.validation_alias
        if isinstance(alias, str):
            names.add(alias.upper())
        else:
            names.update(str(item).upper() for item in getattr(alias, "choices", []))
    for name in list(os.environ):
        if name.upper() in names or name.upper().startswith(("AWS_", "GOOGLE_")):
            os.environ.pop(name)
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"

    original_connect = socket.socket.connect

    def loopback_only(sock, address):
        if isinstance(address, tuple):
            host, port = address[:2]
            try:
                local = host == "localhost" or ipaddress.ip_address(host).is_loopback
            except ValueError:
                local = False
            if not local or port in {5432, 7000, 9000, 9001, 11434}:
                raise OSError("Offline fixture disallows this network destination")
        return original_connect(sock, address)

    socket.socket.connect = loopback_only
    from sqlalchemy import create_engine, text

    fixture_url = "postgresql+psycopg://postgres:vision-fixture-only@127.0.0.1:55437/"
    admin = create_engine(fixture_url + "postgres", isolation_level="AUTOCOMMIT")
    name = "gehihi_suite_" + uuid4().hex
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ["DATABASE_URL"] = fixture_url + name
    get_settings.cache_clear()
    try:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
        import pytest

        return pytest.main([
            "--ignore=tests/test_playwright_worker_compose.py",
            "--basetemp=.pytest_cache/gehihi-final-" + uuid4().hex,
            *sys.argv[1:],
        ])
    finally:
        # UUID database was created above by this invocation; application DB is untouched.
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
        socket.socket.connect = original_connect


if __name__ == "__main__":
    raise SystemExit(main())
