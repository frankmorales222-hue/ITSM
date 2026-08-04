"""Database backup, restore, verification, and SQLite-to-PostgreSQL transfer tools."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select, text, update
from sqlalchemy.engine import URL, make_url

from .config import settings
from .database import Base
from . import models  # noqa: F401 - registers all model tables


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _write_checksum(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{_digest(path)}  {path.name}\n", encoding="ascii"
    )


def _sqlite_path(url: URL) -> Path:
    if not url.database:
        raise ValueError("SQLite database path is missing")
    return Path(url.database).resolve()


def _postgres_args(url: URL) -> tuple[list[str], dict[str, str]]:
    args: list[str] = []
    if url.host:
        args.extend(["--host", url.host])
    if url.port:
        args.extend(["--port", str(url.port)])
    if url.username:
        args.extend(["--username", url.username])
    if url.database:
        args.extend(["--dbname", url.database])
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    return args, environment


def verify_backup(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Backup is missing or empty: {path}")
    checksum = path.with_suffix(path.suffix + ".sha256")
    if checksum.exists() and checksum.read_text(encoding="ascii").split()[0] != _digest(path):
        raise RuntimeError("Backup checksum does not match")
    if path.suffix == ".sqlite":
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"SQLite integrity check failed: {result}")
        finally:
            connection.close()
    elif path.suffix == ".dump":
        executable = shutil.which("pg_restore")
        if not executable:
            raise RuntimeError("pg_restore is required to verify a PostgreSQL backup")
        subprocess.run([executable, "--list", str(path)], check=True, capture_output=True)
    else:
        raise RuntimeError("Backup must end in .sqlite or .dump")


def create_backup(database_url: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        source = _sqlite_path(url)
        if not source.is_file():
            raise RuntimeError(f"SQLite database does not exist: {source}")
        destination = directory / f"itsm-{_timestamp()}.sqlite"
        source_db = sqlite3.connect(str(source))
        target_db = sqlite3.connect(str(destination))
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
            source_db.close()
    elif url.get_backend_name() == "postgresql":
        executable = shutil.which("pg_dump")
        if not executable:
            raise RuntimeError("pg_dump is required for PostgreSQL backups")
        destination = directory / f"itsm-{_timestamp()}.dump"
        connection_args, environment = _postgres_args(url)
        subprocess.run(
            [executable, *connection_args, "--format=custom", "--file", str(destination)],
            env=environment,
            check=True,
        )
    else:
        raise RuntimeError(f"Unsupported database backend: {url.get_backend_name()}")
    _write_checksum(destination)
    verify_backup(destination)
    return destination


def restore_backup(path: Path, database_url: str) -> None:
    verify_backup(path)
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and path.suffix == ".sqlite":
        target = _sqlite_path(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.stem + "-restore.sqlite")
        shutil.copy2(path, temporary)
        verify_backup(temporary)
        os.replace(temporary, target)
        return
    if url.get_backend_name() == "postgresql" and path.suffix == ".dump":
        executable = shutil.which("pg_restore")
        if not executable:
            raise RuntimeError("pg_restore is required for PostgreSQL restore")
        connection_args, environment = _postgres_args(url)
        subprocess.run(
            [executable, *connection_args, "--clean", "--if-exists", "--no-owner", "--exit-on-error", str(path)],
            env=environment,
            check=True,
        )
        return
    raise RuntimeError("Backup type and target database backend do not match")


def _initialize_target(target_url: str) -> None:
    environment = os.environ.copy()
    environment["ITSM_DATABASE_URL"] = target_url
    environment["PYTHONPATH"] = str(Path("backend").resolve())
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
    )


def migrate_sqlite_to_postgres(source_url: str, target_url: str) -> dict[str, int]:
    source_parsed = make_url(source_url)
    target_parsed = make_url(target_url)
    if source_parsed.get_backend_name() != "sqlite":
        raise RuntimeError("Migration source must be SQLite")
    if target_parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Migration target must be PostgreSQL")
    if not _sqlite_path(source_parsed).is_file():
        raise RuntimeError("SQLite source database was not found")

    _initialize_target(target_url)
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url, pool_pre_ping=True)
    copied: dict[str, int] = {}
    try:
        with target_engine.connect() as connection:
            occupied = []
            for table in Base.metadata.sorted_tables:
                if table.name == "alembic_version":
                    continue
                count = connection.execute(select(func.count()).select_from(table)).scalar_one()
                if count:
                    occupied.append(table.name)
            if occupied:
                raise RuntimeError("PostgreSQL target is not empty: " + ", ".join(occupied))

        with source_engine.connect() as source, target_engine.begin() as target:
            employee_managers: list[tuple[int, int]] = []
            for table in Base.metadata.sorted_tables:
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if table.name == "employees":
                    employee_managers = [(row["id"], row["manager_id"]) for row in rows if row.get("manager_id")]
                    for row in rows:
                        row["manager_id"] = None
                if rows:
                    target.execute(insert(table), rows)
                copied[table.name] = len(rows)
            employee_table = Base.metadata.tables["employees"]
            for employee_id, manager_id in employee_managers:
                target.execute(
                    update(employee_table).where(employee_table.c.id == employee_id).values(manager_id=manager_id)
                )
            for table in Base.metadata.sorted_tables:
                integer_pk = next((column for column in table.primary_key.columns if str(column.type).startswith("INTEGER")), None)
                if integer_pk is not None:
                    sequence = target.execute(
                        text("SELECT pg_get_serial_sequence(:table, :column)"),
                        {"table": table.name, "column": integer_pk.name},
                    ).scalar_one_or_none()
                    if sequence:
                        maximum = target.execute(select(func.max(integer_pk))).scalar_one_or_none()
                        target.execute(
                            text("SELECT setval(CAST(:sequence AS regclass), :value, :used)"),
                            {"sequence": sequence, "value": maximum or 1, "used": maximum is not None},
                        )
    finally:
        source_engine.dispose()
        target_engine.dispose()
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--database-url", default=settings.database_url)
    backup.add_argument("--directory", type=Path, default=Path(settings.backup_directory))
    verify = commands.add_parser("verify")
    verify.add_argument("path", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("path", type=Path)
    restore.add_argument("--database-url", default=settings.database_url)
    restore.add_argument("--confirm", required=True)
    migrate = commands.add_parser("migrate-to-postgres")
    migrate.add_argument("--source", default="sqlite:///./data/itsm.db")
    destination = migrate.add_mutually_exclusive_group(required=True)
    destination.add_argument("--target")
    destination.add_argument("--target-env", action="store_true", help="Read target URL from ITSM_MIGRATION_TARGET_URL")
    args = parser.parse_args()

    if args.command == "backup":
        result = create_backup(args.database_url, args.directory)
        print(f"Verified backup created: {result}")
    elif args.command == "verify":
        verify_backup(args.path)
        print(f"Backup verified: {args.path}")
    elif args.command == "restore":
        if args.confirm != "RESTORE":
            raise RuntimeError("Restore refused; --confirm must be exactly RESTORE")
        restore_backup(args.path, args.database_url)
        print("Restore completed and verified")
    else:
        target_url = os.environ.get("ITSM_MIGRATION_TARGET_URL") if args.target_env else args.target
        if not target_url:
            raise RuntimeError("PostgreSQL target URL was not provided")
        backup_path = create_backup(args.source, Path(settings.backup_directory))
        print(f"Source backup verified: {backup_path}")
        copied = migrate_sqlite_to_postgres(args.source, target_url)
        print(f"Migration completed: {sum(copied.values())} rows across {len(copied)} tables")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
