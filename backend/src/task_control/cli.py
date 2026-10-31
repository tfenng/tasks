from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func, select

from task_control.config import get_settings
from task_control.infrastructure.db.models import User
from task_control.infrastructure.db.session import create_all, session_scope
from task_control.infrastructure.security.passwords import hash_password


def _password(value: str | None) -> str:
    if value:
        return value
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("passwords do not match")
    if len(first) < 12:
        raise SystemExit("password must be at least 12 characters")
    return first


def create_admin(args: argparse.Namespace) -> int:
    create_all()
    with session_scope() as db:
        existing = db.scalar(select(User).where(func.lower(User.username) == args.username.lower()))
        if existing is not None:
            print(f"user already exists: {args.username}", file=sys.stderr)
            return 1
        db.add(
            User(
                username=args.username,
                display_name=args.display_name or args.username,
                password_hash=hash_password(_password(args.password)),
                role="admin",
            )
        )
    print(f"created admin: {args.username}")
    return 0


def reset_password(args: argparse.Namespace) -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == args.username.lower()))
        if user is None:
            print(f"user not found: {args.username}", file=sys.stderr)
            return 1
        user.password_hash = hash_password(_password(args.password))
        user.must_change_password = True
        user.version += 1
    print(f"password reset: {args.username}")
    return 0


def retention(_: argparse.Namespace) -> int:
    from task_control.worker.retention import run_retention

    result = run_retention()
    print(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="task-control")
    sub = parser.add_subparsers(dest="command", required=True)
    retention_parser = sub.add_parser("retention")
    retention_parser.set_defaults(func=retention)
    admin = sub.add_parser("create-admin")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name")
    admin.add_argument("--password")
    admin.set_defaults(func=create_admin)
    reset = sub.add_parser("reset-password")
    reset.add_argument("--username", required=True)
    reset.add_argument("--password")
    reset.set_defaults(func=reset_password)
    args = parser.parse_args(argv)
    get_settings()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
