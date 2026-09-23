"""Database backup, restore, verification, and SQLite-to-PostgreSQL transfer tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select, text, update
from sqlalchemy.engine import URL, make_url

from .config import settings
from .database import Base
from . import models  # noqa: F401 - registers all model tables


def _postgres_tool(name: str) -> str | None:
    """Find PostgreSQL utilities even when its installer did not update PATH."""
    executable = shutil.which(name)
    if executable:
        return executable
    executable_name = name + (".exe" if os.name == "nt" and not name.endswith(".exe") else "")
    roots = {
        Path(value) / "PostgreSQL"
        for key in ("ProgramFiles", "ProgramW6432")
        if (value := os.environ.get(key))
    }
    candidates = [candidate for root in roots if root.is_dir()
                  for candidate in root.glob(f"*/bin/{executable_name}") if candidate.is_file()]
    if not candidates:
        return None

    def version_key(path: Path) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in path.parents[1].name.split("."))
        except ValueError:
            return (0,)

    return str(max(candidates, key=version_key))


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


def latest_verified_backup(directory: Path) -> Path:
    candidates = sorted(
        (
            path
            for suffix in ("*.dump", "*.sqlite")
            for path in directory.glob(suffix)
            if path.is_file()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    errors: list[str] = []
    for candidate in candidates:
        try:
            verify_backup(candidate)
            return candidate
        except Exception as exc:  # pragma: no cover - details are surfaced to operators
            errors.append(f"{candidate.name}: {exc}")
    detail = "; ".join(errors) if errors else "no .dump or .sqlite files found"
    raise RuntimeError(f"No verified Northstar backup is available in {directory}: {detail}")


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
        executable = _postgres_tool("pg_restore")
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
        executable = _postgres_tool("pg_dump")
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
        executable = _postgres_tool("pg_restore")
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


SERVER_LOCAL_ENV_KEYS = {
    "ITSM_DATABASE_URL",
    "ITSM_DATA_DIRECTORY",
    "ITSM_BACKUP_DIRECTORY",
    "ITSM_UPDATE_STAGING_DIRECTORY",
    "ITSM_PUBLIC_URL",
    "ITSM_ALLOWED_ORIGINS",
    "ITSM_TRUSTED_HOSTS",
    "ITSM_FORWARDED_ALLOW_IPS",
    "ITSM_BIND_HOST",
    "ITSM_PORT",
    "ITSM_HTTPS_PORT",
    "ITSM_OUTBOUND_EMAIL_ENABLED",
    "ITSM_STATIC_DIRECTORY",
    "ITSM_ASSETPILOT_EXECUTABLE",
    "ITSM_ASSETPILOT_DATABASE_PATH",
    "ITSM_ASSETPILOT_URL",
    "ITSM_ASSETPILOT_INTERNAL_URL",
    "ITSM_ASSETPILOT_PORT",
}


def _read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return lines, values


def _merge_env_files(imported_env: Path, current_env: Path) -> list[str]:
    imported_lines, _imported = _read_env(imported_env)
    current_lines, current_values = _read_env(current_env)
    output: list[str] = []
    seen: set[str] = set()
    for line in imported_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0]
        seen.add(key)
        if key in SERVER_LOCAL_ENV_KEYS and key in current_values:
            output.append(f"{key}={current_values[key]}")
        else:
            output.append(line)
    for line in current_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0]
        if key in SERVER_LOCAL_ENV_KEYS and key not in seen:
            output.append(line)
    return output


def create_migration_package(
    data_root: Path,
    output_path: Path,
    backup_path: Path | None = None,
) -> Path:
    env_path = data_root / ".env"
    if not env_path.is_file():
        raise RuntimeError(f"Northstar configuration was not found: {env_path}")
    _, env_values = _read_env(env_path)
    backup_directory = Path(
        env_values.get("ITSM_BACKUP_DIRECTORY", str(data_root / "backups")).strip('"')
    )
    if backup_path is None:
        database_url = env_values.get("ITSM_DATABASE_URL", "").strip('"')
        if not database_url:
            raise RuntimeError("ITSM_DATABASE_URL is missing from Northstar configuration")
        selected_backup = create_backup(database_url, backup_directory)
    else:
        selected_backup = backup_path
    verify_backup(selected_backup)
    attachments_root = data_root / "data" / "attachments"
    attachment_files = (
        [path for path in attachments_root.rglob("*") if path.is_file()]
        if attachments_root.is_dir()
        else []
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "product": "Northstar Desk",
        "format": "northstar-server-migration-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
        "backup": selected_backup.name,
        "backup_sha256": _digest(selected_backup),
        "contains_env": True,
        "attachment_files": len(attachment_files),
        "notes": [
            "Package contains configuration secrets; store and transfer securely.",
            "Windows Credential Manager secrets are not included and may need re-entry.",
        ],
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.write(env_path, "config/.env")
        if (data_root / "Caddyfile").is_file():
            archive.write(data_root / "Caddyfile", "config/Caddyfile")
        archive.write(selected_backup, f"backups/{selected_backup.name}")
        checksum = selected_backup.with_suffix(selected_backup.suffix + ".sha256")
        if checksum.is_file():
            archive.write(checksum, f"backups/{checksum.name}")
        for attachment in attachment_files:
            relative = attachment.relative_to(attachments_root).as_posix()
            archive.write(attachment, f"data/attachments/{relative}")
    return output_path


def restore_migration_package(package_path: Path, data_root: Path, database_url: str) -> Path:
    if not package_path.is_file():
        raise RuntimeError(f"Migration package was not found: {package_path}")
    env_path = data_root / ".env"
    if not env_path.is_file():
        raise RuntimeError("Install and configure the new server before importing a migration package.")
    staging = data_root / "migration-import"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(package_path) as archive:
            for member in archive.infolist():
                destination = (staging / member.filename).resolve()
                if not str(destination).startswith(str(staging.resolve()) + os.sep):
                    raise RuntimeError("Migration package contains an unsafe path")
                archive.extract(member, staging)
        manifest_path = staging / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError("Migration package manifest is missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != "northstar-server-migration-v1":
            raise RuntimeError("Migration package format is not supported")
        backups = sorted((staging / "backups").glob("itsm-*.dump")) or sorted(
            (staging / "backups").glob("itsm-*.sqlite")
        )
        if not backups:
            raise RuntimeError("Migration package does not contain a Northstar database backup")
        backup = backups[0]
        expected_digest = manifest.get("backup_sha256")
        if expected_digest and _digest(backup) != expected_digest:
            raise RuntimeError("Packaged backup checksum does not match the manifest")
        restore_backup(backup, database_url)
        imported_env = staging / "config" / ".env"
        if imported_env.is_file():
            backup_env = env_path.with_name(f".env.before-migration-{_timestamp()}")
            shutil.copy2(env_path, backup_env)
            env_path.write_text("\n".join(_merge_env_files(imported_env, env_path)) + "\n", encoding="utf-8")
        attachments = staging / "data" / "attachments"
        if attachments.is_dir():
            target_attachments = data_root / "data" / "attachments"
            target_attachments.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(attachments, target_attachments, dirs_exist_ok=True)
        return backup
    finally:
        shutil.rmtree(staging, ignore_errors=True)


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
    package = commands.add_parser("package-migration")
    package.add_argument("--data-root", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--backup-path", type=Path)
    import_package = commands.add_parser("import-migration")
    import_package.add_argument("package", type=Path)
    import_package.add_argument("--data-root", type=Path, required=True)
    import_package.add_argument("--database-url", default=settings.database_url)
    import_package.add_argument("--confirm", required=True)
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
    elif args.command == "package-migration":
        result = create_migration_package(args.data_root, args.output, args.backup_path)
        print(f"Migration package created: {result}")
    elif args.command == "import-migration":
        if args.confirm != "IMPORT":
            raise RuntimeError("Import refused; --confirm must be exactly IMPORT")
        backup = restore_migration_package(args.package, args.data_root, args.database_url)
        print(f"Migration package imported from backup: {backup.name}")
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
