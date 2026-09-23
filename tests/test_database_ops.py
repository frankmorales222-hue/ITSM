from pathlib import Path
import zipfile

from itsm import database_ops


def test_postgres_tool_is_discovered_outside_path(tmp_path, monkeypatch):
    program_files = tmp_path / "Program Files"
    old_tool = program_files / "PostgreSQL" / "16" / "bin" / "pg_dump.exe"
    current_tool = program_files / "PostgreSQL" / "18" / "bin" / "pg_dump.exe"
    old_tool.parent.mkdir(parents=True)
    current_tool.parent.mkdir(parents=True)
    old_tool.write_bytes(b"old")
    current_tool.write_bytes(b"current")

    monkeypatch.setattr(database_ops.shutil, "which", lambda _name: None)
    monkeypatch.setattr(database_ops.os, "name", "nt")
    monkeypatch.setenv("ProgramFiles", str(program_files))
    monkeypatch.delenv("ProgramW6432", raising=False)

    assert Path(database_ops._postgres_tool("pg_dump")) == current_tool


def test_migration_package_contains_env_and_verified_backup(tmp_path, monkeypatch):
    data_root = tmp_path / "ProgramData" / "NorthstarDesk"
    backup_dir = data_root / "backups"
    backup_dir.mkdir(parents=True)
    env = data_root / ".env"
    env.write_text(
        "ITSM_DATABASE_URL=postgresql+psycopg://old:secret@old-db/northstar_desk\n"
        f"ITSM_BACKUP_DIRECTORY={backup_dir}\n"
        "ITSM_MICROSOFT_CLIENT_ID=old-client\n",
        encoding="utf-8",
    )
    backup = backup_dir / "itsm-20260827-120000Z.dump"
    backup.write_bytes(b"postgres dump")
    attachment = data_root / "data" / "attachments" / "1-evidence.txt"
    attachment.parent.mkdir(parents=True)
    attachment.write_text("attachment body", encoding="utf-8")
    monkeypatch.setattr(database_ops, "create_backup", lambda _database_url, _backup_dir: backup)
    monkeypatch.setattr(database_ops, "verify_backup", lambda path: None)

    package = database_ops.create_migration_package(
        data_root, tmp_path / "NorthstarDesk-Migration.zip", backup
    )

    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "config/.env" in names
        assert "backups/itsm-20260827-120000Z.dump" in names
        assert "data/attachments/1-evidence.txt" in names


def test_migration_package_creates_fresh_backup_when_not_supplied(tmp_path, monkeypatch):
    data_root = tmp_path / "ProgramData" / "NorthstarDesk"
    backup_dir = data_root / "backups"
    data_root.mkdir(parents=True)
    (data_root / ".env").write_text(
        "ITSM_DATABASE_URL=postgresql+psycopg://service:secret@db/northstar\n"
        f"ITSM_BACKUP_DIRECTORY={backup_dir}\n",
        encoding="utf-8",
    )
    fresh = backup_dir / "itsm-fresh.dump"

    def fake_backup(database_url, directory):
        assert database_url == "postgresql+psycopg://service:secret@db/northstar"
        assert directory == backup_dir
        directory.mkdir(parents=True)
        fresh.write_bytes(b"fresh")
        return fresh

    monkeypatch.setattr(database_ops, "create_backup", fake_backup)
    monkeypatch.setattr(database_ops, "verify_backup", lambda path: None)

    package = database_ops.create_migration_package(data_root, tmp_path / "migration.zip")

    with zipfile.ZipFile(package) as archive:
        assert "backups/itsm-fresh.dump" in archive.namelist()


def test_restore_migration_package_restores_attachments(tmp_path, monkeypatch):
    data_root = tmp_path / "new-server"
    data_root.mkdir()
    (data_root / ".env").write_text(
        "ITSM_DATABASE_URL=sqlite:///new.sqlite\nITSM_PUBLIC_URL=https://new.example.test\n",
        encoding="utf-8",
    )
    package = tmp_path / "migration.zip"
    backup_bytes = b"database backup"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "manifest.json",
            '{"format":"northstar-server-migration-v1","backup_sha256":"'
            + database_ops.hashlib.sha256(backup_bytes).hexdigest()
            + '"}',
        )
        archive.writestr("backups/itsm-test.sqlite", backup_bytes)
        archive.writestr("config/.env", "ITSM_SECRET_KEY=old-secret\n")
        archive.writestr("data/attachments/ticket-2/screenshot.png", b"image")
    monkeypatch.setattr(database_ops, "restore_backup", lambda path, url: None)

    database_ops.restore_migration_package(package, data_root, "sqlite:///new.sqlite")

    assert (data_root / "data" / "attachments" / "ticket-2" / "screenshot.png").read_bytes() == b"image"
    merged = (data_root / ".env").read_text(encoding="utf-8")
    assert "ITSM_DATABASE_URL=sqlite:///new.sqlite" in merged
    assert "ITSM_SECRET_KEY=old-secret" in merged


def test_migration_env_merge_preserves_new_server_connection_settings(tmp_path):
    imported = tmp_path / "imported.env"
    current = tmp_path / "current.env"
    imported.write_text(
        "ITSM_DATABASE_URL=postgresql+psycopg://old:secret@old-db/northstar_desk\n"
        "ITSM_PUBLIC_URL=https://old-helpdesk.example.test\n"
        "ITSM_OUTBOUND_EMAIL_ENABLED=true\n"
        "ITSM_SECRET_KEY=old-secret-key\n"
        "ITSM_MICROSOFT_CLIENT_ID=old-client\n",
        encoding="utf-8",
    )
    current.write_text(
        "ITSM_DATABASE_URL=postgresql+psycopg://new:secret@new-db/northstar_desk\n"
        "ITSM_PUBLIC_URL=https://new-helpdesk.example.test\n"
        "ITSM_OUTBOUND_EMAIL_ENABLED=false\n"
        "ITSM_PORT=8011\n",
        encoding="utf-8",
    )

    merged = "\n".join(database_ops._merge_env_files(imported, current))

    assert "ITSM_DATABASE_URL=postgresql+psycopg://new:secret@new-db/northstar_desk" in merged
    assert "ITSM_PUBLIC_URL=https://new-helpdesk.example.test" in merged
    assert "ITSM_OUTBOUND_EMAIL_ENABLED=false" in merged
    assert "ITSM_SECRET_KEY=old-secret-key" in merged
    assert "ITSM_MICROSOFT_CLIENT_ID=old-client" in merged
    assert "ITSM_PORT=8011" in merged
