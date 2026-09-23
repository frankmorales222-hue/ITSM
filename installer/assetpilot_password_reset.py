"""Offline recovery utility for AssetPilot ASP.NET Identity administrators."""

from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import hashlib
import os
import re
import struct
import sys
import uuid
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text


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


def aspnet_identity_v3_hash(
    password: str,
    *,
    salt: bytes | None = None,
    iterations: int = 100_000,
) -> str:
    """Create the format emitted by ASP.NET Core Identity PasswordHasher.

    Format marker 0x01 is followed by big-endian PRF (HMAC-SHA512 = 2),
    iteration count, salt length, salt, and a 32-byte PBKDF2 subkey.
    """
    salt = salt or os.urandom(16)
    if len(salt) < 16:
        raise ValueError("ASP.NET Identity salt must be at least 16 bytes")
    subkey = hashlib.pbkdf2_hmac(
        "sha512", password.encode("utf-8"), salt, iterations, dklen=32
    )
    payload = (
        b"\x01"
        + struct.pack(">I", 2)
        + struct.pack(">I", iterations)
        + struct.pack(">I", len(salt))
        + salt
        + subkey
    )
    return base64.b64encode(payload).decode("ascii")


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
            "Access to the protected server configuration was denied. "
            "Right-click this utility and select Run as administrator."
        ) from exc
    database_url = (values.get("ITSM_DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("ITSM_DATABASE_URL is missing from the server configuration.")
    return database_url


def discover_identity_schema(connection) -> str:
    schemas = connection.execute(text(
        "SELECT table_schema FROM information_schema.tables "
        "WHERE table_name = 'AspNetUsers' "
        "ORDER BY CASE table_schema WHEN 'assetpilot' THEN 0 WHEN 'public' THEN 1 ELSE 2 END"
    )).scalars().all()
    if not schemas:
        raise RuntimeError("AssetPilot identity tables were not found in PostgreSQL.")
    schema = str(schemas[0])
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise RuntimeError("AssetPilot returned an unsafe database schema name.")
    return schema


def administrator_accounts(connection, schema: str) -> list[dict]:
    query = text(
        f'SELECT u."Id", u."UserName", u."Email", u."DisplayName" '
        f'FROM "{schema}"."AspNetUsers" u '
        f'JOIN "{schema}"."AspNetUserRoles" ur ON ur."UserId" = u."Id" '
        f'JOIN "{schema}"."AspNetRoles" r ON r."Id" = ur."RoleId" '
        f'WHERE upper(r."NormalizedName") = \'ADMINISTRATOR\' '
        f'ORDER BY u."Email", u."UserName"'
    )
    return [dict(row) for row in connection.execute(query).mappings().all()]


def reset_assetpilot_admin(data_root: Path, user_id: str, new_password: str) -> dict:
    errors = password_errors(new_password)
    if errors:
        raise ValueError("; ".join(errors))
    engine = create_engine(read_database_url(data_root), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            schema = discover_identity_schema(connection)
            accounts = administrator_accounts(connection, schema)
            matches = [account for account in accounts if str(account["Id"]) == user_id]
            if len(matches) != 1:
                raise RuntimeError("The selected AssetPilot administrator was not found.")
            password_hash = aspnet_identity_v3_hash(new_password)
            result = connection.execute(
                text(
                    f'UPDATE "{schema}"."AspNetUsers" SET '
                    f'"PasswordHash" = :password_hash, "AccessFailedCount" = 0, '
                    f'"LockoutEnd" = NULL, "SecurityStamp" = :security_stamp, '
                    f'"ConcurrencyStamp" = :concurrency_stamp WHERE "Id" = :user_id'
                ),
                {
                    "password_hash": password_hash,
                    "security_stamp": uuid.uuid4().hex.upper(),
                    "concurrency_stamp": str(uuid.uuid4()),
                    "user_id": user_id,
                },
            )
            if result.rowcount != 1:
                raise RuntimeError("The AssetPilot password update was not applied.")
            return matches[0]
    finally:
        engine.dispose()


def choose_account(accounts: list[dict]) -> dict:
    if not accounts:
        raise RuntimeError("No AssetPilot users have the Administrator role.")
    print("AssetPilot administrator accounts:")
    for index, account in enumerate(accounts, start=1):
        label = account.get("Email") or account.get("UserName") or account.get("Id")
        display = account.get("DisplayName") or ""
        print(f"  {index}. {label} {('- ' + display) if display else ''}")
    while True:
        selected = input("Select the account number to reset: ").strip()
        try:
            return accounts[int(selected) - 1]
        except (ValueError, IndexError):
            print("Enter one of the account numbers shown above.")


def prompt_for_password() -> str:
    while True:
        password = getpass.getpass("New AssetPilot administrator password: ")
        errors = password_errors(password)
        if errors:
            print("Password requirements: " + "; ".join(errors))
            continue
        confirmation = getpass.getpass("Confirm new password: ")
        if password != confirmation:
            print("The passwords do not match. Try again.")
            continue
        return password


def self_test() -> int:
    import psycopg
    from psycopg import pq

    sample = "AssetPilot-Recovery-2026!"
    encoded = aspnet_identity_v3_hash(
        sample, salt=bytes(range(16)), iterations=100_000
    )
    decoded = base64.b64decode(encoded)
    if decoded[0] != 1 or struct.unpack(">I", decoded[1:5])[0] != 2:
        raise RuntimeError("ASP.NET Identity hash-format self-test failed.")
    if not psycopg.__version__ or pq.version() <= 0:
        raise RuntimeError("Packaged PostgreSQL driver self-test failed.")
    print("AssetPilot administrator recovery self-test passed.")
    print(f"DOTNET_TEST_HASH={encoded}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset an AssetPilot administrator password")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("ProgramData", "C:/ProgramData")) / "NorthstarDesk",
    )
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    print("AssetPilot - Administrator Password Recovery")
    print("This changes only a selected AssetPilot Administrator account.")
    print()
    if not is_windows_administrator():
        raise RuntimeError("Right-click this utility and select Run as administrator.")
    engine = create_engine(read_database_url(args.data_root.resolve()), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            schema = discover_identity_schema(connection)
            account = choose_account(administrator_accounts(connection, schema))
    finally:
        engine.dispose()
    password = prompt_for_password()
    reset = reset_assetpilot_admin(args.data_root.resolve(), str(account["Id"]), password)
    print()
    print(f"Password reset completed for {reset.get('Email') or reset.get('UserName')}.")
    print("You can now sign in to AssetPilot with that email and the new password.")
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

