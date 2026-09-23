"""Offline recovery utility for the local Northstar administrator account.

This utility intentionally runs outside the web application. It reads the
protected production configuration, updates exactly one local administrator,
and revokes that account's existing sessions. Passwords are never accepted as
command-line arguments or written to disk/logs.
"""

from __future__ import annotations

import argparse
import ctypes
import getpass
import os
import re
import sys
from pathlib import Path

from argon2 import PasswordHasher
from dotenv import dotenv_values
from sqlalchemy import create_engine, text


PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def password_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 12:
        errors.append("Use at least 12 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("Add an uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("Add a lowercase letter")
    if not re.search(r"\d", password):
        errors.append("Add a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Add a symbol")
    return errors


def is_windows_administrator() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def read_database_url(data_root: Path) -> str:
    config = data_root / ".env"
    if not config.is_file():
        raise RuntimeError(f"Northstar configuration was not found: {config}")
    try:
        values = dotenv_values(config)
    except PermissionError as exc:
        raise RuntimeError(
            "Access to the protected Northstar configuration was denied. "
            "Right-click this utility and select Run as administrator."
        ) from exc
    database_url = (values.get("ITSM_DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("ITSM_DATABASE_URL is missing from the Northstar configuration.")
    return database_url


def reset_local_admin(data_root: Path, username: str, new_password: str) -> int:
    errors = password_errors(new_password)
    if errors:
        raise ValueError("; ".join(errors))
    database_url = read_database_url(data_root)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            accounts = connection.execute(
                text(
                    "SELECT id, username, email, role, auth_source "
                    "FROM users WHERE lower(username) = lower(:username)"
                ),
                {"username": username},
            ).mappings().all()
            if not accounts:
                raise RuntimeError(f"Northstar account '{username}' was not found.")
            if len(accounts) != 1:
                raise RuntimeError(
                    f"More than one account matched '{username}'; no changes were made."
                )
            account = accounts[0]
            if str(account["role"]).lower() != "admin":
                raise RuntimeError(
                    f"Account '{username}' is not a Northstar administrator; no changes were made."
                )
            password_hash = PASSWORD_HASHER.hash(new_password)
            result = connection.execute(
                text(
                    "UPDATE users SET password_hash = :password_hash, active = true, "
                    "must_change_password = false, failed_attempts = 0, locked_until = NULL, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = :user_id"
                ),
                {"password_hash": password_hash, "user_id": account["id"]},
            )
            if result.rowcount != 1:
                raise RuntimeError("The administrator password update was not applied.")
            connection.execute(
                text("DELETE FROM sessions WHERE user_id = :user_id"),
                {"user_id": account["id"]},
            )
            return int(account["id"])
    finally:
        engine.dispose()


def prompt_for_password() -> str:
    while True:
        password = getpass.getpass("New administrator password: ")
        errors = password_errors(password)
        if errors:
            print("Password requirements: " + "; ".join(errors))
            continue
        confirmation = getpass.getpass("Confirm new administrator password: ")
        if password != confirmation:
            print("The passwords do not match. Try again.")
            continue
        return password


def self_test() -> int:
    import psycopg
    from psycopg import pq

    sample = "Northstar-Recovery-2026!"
    encoded = PASSWORD_HASHER.hash(sample)
    if not PASSWORD_HASHER.verify(encoded, sample):
        raise RuntimeError("Password hashing self-test failed.")
    if password_errors(sample):
        raise RuntimeError("Password validation self-test failed.")
    if not psycopg.__version__ or pq.version() <= 0:
        raise RuntimeError("Packaged PostgreSQL driver self-test failed.")
    engine = create_engine(
        "postgresql+psycopg://selftest:selftest@127.0.0.1:1/selftest",
        connect_args={"connect_timeout": 1},
    )
    engine.dispose()
    print("Northstar administrator recovery self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a local Northstar administrator password")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("ProgramData", "C:/ProgramData")) / "NorthstarDesk",
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    print("Northstar Desk - Local Administrator Password Recovery")
    print("This changes only the selected local administrator account.")
    print()
    if not is_windows_administrator():
        raise RuntimeError("Right-click this utility and select Run as administrator.")
    password = prompt_for_password()
    user_id = reset_local_admin(args.data_root.resolve(), args.username.strip(), password)
    print()
    print(f"Password reset completed for '{args.username}' (account ID {user_id}).")
    print("Existing sessions for this account were revoked. You can now sign in locally.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nPassword reset cancelled.")
        raise SystemExit(2)
    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        print("No password was written to a file or displayed.")
        if getattr(sys, "frozen", False):
            input("Press Enter to close...")
        raise SystemExit(1)
