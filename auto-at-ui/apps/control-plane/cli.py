"""Operational commands; invoke with ``uv run python apps/control-plane/cli.py``."""

import argparse
import getpass

from application.authentication import AccountService, AuthenticationError, PasswordPolicyError
from config import get_settings
from infrastructure.persistence.session import create_session_factory, transactional_session


def main() -> None:
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest="command", required=True)
    bootstrap = command.add_parser("bootstrap-admin")
    bootstrap.add_argument("--tenant", required=True)
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--temporary-password")
    args = parser.parse_args()
    password = args.temporary_password or getpass.getpass("Temporary password: ")
    try:
        with transactional_session(create_session_factory(get_settings())) as session:
            account = AccountService(session).bootstrap_admin(args.tenant, args.email, password)
    except (AuthenticationError, PasswordPolicyError) as error:
        parser.error(str(error))
    print(f"Tenant admin ready: {account.email} ({args.tenant})")


if __name__ == "__main__":
    main()
