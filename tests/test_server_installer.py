from pathlib import Path
import os
import re

import pytest
import sqlalchemy

from installer import server_entry


def test_postgresql_alembic_version_column_fits_every_revision():
    revision_files = sorted(Path("migrations/versions").glob("*.py"))
    revision_ids = []
    for revision_file in revision_files:
        text = revision_file.read_text(encoding="utf-8")
        match = re.search(r'^revision\s*=\s*["\']([^"\']+)', text, re.MULTILINE)
        assert match, f"Missing revision identifier in {revision_file}"
        revision_ids.append(match.group(1))

    first_widening_migration = Path(
        "migrations/versions/0006_remove_legacy_asset_source_index.py"
    ).read_text(encoding="utf-8")
    legacy_resume_migration = Path(
        "migrations/versions/0010_administration_control_plane.py"
    ).read_text(encoding="utf-8")
    server_entry_text = Path("installer/server_entry.py").read_text(encoding="utf-8")
    assert max(map(len, revision_ids)) <= 128
    assert '"alembic_version"' in first_widening_migration
    assert "type_=sa.String(length=128)" in first_widening_migration
    assert '"alembic_version"' in legacy_resume_migration
    assert "type_=sa.String(length=128)" in legacy_resume_migration
    assert "ensure_alembic_version_capacity(settings.database_url)" in server_entry_text


def test_legacy_postgresql_version_column_is_repaired_before_resume(monkeypatch):
    executed = []

    class FakeConnection:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def execute(self, statement):
            executed.append(str(statement))

    class FakeTransaction:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, *_args):
            return False

    class FakeEngine:
        disposed = False

        def begin(self):
            return FakeTransaction()

        def dispose(self):
            self.disposed = True

    class FakeInspector:
        def get_table_names(self):
            return ["alembic_version", "organizations"]

        def get_columns(self, _table):
            return [{"name": "version_num", "type": sqlalchemy.String(length=32)}]

    engine = FakeEngine()
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(sqlalchemy, "inspect", lambda _connection: FakeInspector())

    server_entry.ensure_alembic_version_capacity(
        "postgresql+psycopg://service:redacted@example.invalid/northstar"
    )

    assert executed == [
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"
    ]
    assert engine.disposed


def test_production_configuration_uses_shared_postgresql(tmp_path, monkeypatch):
    monkeypatch.setattr(server_entry.subprocess, "run", lambda *args, **kwargs: None)
    server_entry.write_production_config(
        tmp_path,
        "Example Support",
        "helpdesk.example.test",
        "assets.example.test",
        "db01.example.test",
        5432,
        "northstar_desk",
        "itsm_service",
        "generated-service-password",
        tmp_path / "backups",
        8443,
        8011,
        5081,
    )

    northstar = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "postgresql+psycopg://itsm_service:generated-service-password@db01.example.test:5432/northstar_desk" in northstar
    assert "ITSM_ASSETPILOT_ENABLED=false" in northstar
    assert "ITSM_ASSETPILOT_DATABASE_PATH" not in northstar
    assert "ITSM_PORT=8011" in northstar
    assert "ITSM_HTTPS_PORT=8443" in northstar
    assert "ITSM_PUBLIC_URL=https://helpdesk.example.test:8443" in northstar
    assert not (tmp_path / "AssetPilot").exists()
    caddy = (tmp_path / "Caddyfile").read_text(encoding="utf-8")
    assert "https://helpdesk.example.test:8443" in caddy
    assert "reverse_proxy 127.0.0.1:8011" in caddy
    assert "5081" not in caddy


def test_production_configuration_can_import_old_server_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(server_entry.subprocess, "run", lambda *args, **kwargs: None)
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    old_config = old_root / ".env"
    old_config.write_text(
        "ITSM_ENVIRONMENT=production\n"
        "ITSM_DATABASE_URL=\"postgresql+psycopg://old:old@old-server/northstar_desk\"\n"
        "ITSM_SECRET_KEY=preserve-this-key-for-database-secrets\n"
        "ITSM_PUBLIC_URL=https://old-helpdesk.example.test\n"
        "ITSM_SMTP_HOST=smtp.example.test\n"
        "ITSM_SMTP_USERNAME=helpdesk@example.test\n"
        "ITSM_OUTBOUND_EMAIL_ENABLED=true\n"
        "ITSM_ASSETPILOT_DATABASE_PATH=C:/ProgramData/NorthstarDesk/AssetPilot/Data/assetpilot.db\n",
        encoding="utf-8",
    )

    server_entry.write_production_config(
        new_root,
        "Example Support",
        "helpdesk.example.test",
        "assets.example.test",
        "new-db.example.test",
        5432,
        "northstar_desk",
        "itsm_service",
        "new-service-password",
        new_root / "backups",
        source_env=old_config,
    )

    northstar = (new_root / ".env").read_text(encoding="utf-8")
    assert "ITSM_SECRET_KEY=preserve-this-key-for-database-secrets" in northstar
    assert "new-service-password@new-db.example.test:5432/northstar_desk" in northstar
    assert "old-server" not in northstar
    assert "ITSM_PUBLIC_URL=https://helpdesk.example.test" in northstar
    assert "ITSM_SMTP_HOST=\"smtp.example.test\"" in northstar
    assert "ITSM_SMTP_USERNAME=\"helpdesk@example.test\"" in northstar
    assert "ITSM_OUTBOUND_EMAIL_ENABLED=false" in northstar
    assert "ITSM_ASSETPILOT_DATABASE_PATH" not in northstar


def test_restored_data_copy_includes_ticket_attachments(tmp_path):
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    attachment = old_root / "data" / "attachments" / "ticket-file.txt"
    attachment.parent.mkdir(parents=True)
    attachment.write_text("supporting evidence", encoding="utf-8")

    server_entry.copy_restored_data_files(old_root, new_root)

    copied = new_root / "data" / "attachments" / "ticket-file.txt"
    assert copied.read_text(encoding="utf-8") == "supporting evidence"


def test_service_ports_must_be_valid_and_distinct():
    server_entry.validate_service_ports(8443, 8011, 5081)
    with pytest.raises(ValueError, match="different ports"):
        server_entry.validate_service_ports(8443, 8443, 5081)
    with pytest.raises(ValueError, match="between 1 and 65535"):
        server_entry.validate_service_ports(70000, 8011, 5081)


def test_internal_readiness_probe_uses_configured_public_host():
    request = server_entry.internal_health_request(
        "http://127.0.0.1:18011/api/health/ready",
        "https://helpdesk.example.test:18443",
    )
    assert request.full_url == "http://127.0.0.1:18011/api/health/ready"
    assert request.get_header("Host") == "helpdesk.example.test"


def test_existing_install_ports_can_change_without_rotating_secret(tmp_path):
    (tmp_path / ".env").write_text(
        "ITSM_SECRET_KEY=keep-this-key\n"
        "ITSM_PUBLIC_URL=https://desk.example.test\n"
        "ITSM_ALLOWED_ORIGINS=https://desk.example.test\n"
        "ITSM_PORT=8000\n"
        "ITSM_HTTPS_PORT=443\n"
        "ITSM_ASSETPILOT_URL=https://assets.example.test\n"
        "ITSM_ASSETPILOT_PORT=5080\n"
        "ITSM_ASSETPILOT_INTERNAL_URL=http://127.0.0.1:5080\n",
        encoding="utf-8",
    )
    server_entry.configure_service_ports(tmp_path, 8443, 8011, 5081)

    northstar = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ITSM_SECRET_KEY=keep-this-key" in northstar
    assert "ITSM_PUBLIC_URL=https://desk.example.test:8443" in northstar
    assert "ITSM_PORT=8011" in northstar
    assert "ITSM_ASSETPILOT_PORT=5080" in northstar
    assert "ITSM_ASSETPILOT_INTERNAL_URL=http://127.0.0.1:5080" in northstar


def test_upgrade_replaces_legacy_loopback_public_addresses(tmp_path):
    (tmp_path / ".env").write_text(
        "ITSM_SECRET_KEY=keep-this-key\n"
        "ITSM_PUBLIC_URL=http://127.0.0.1:8000\n"
        "ITSM_ALLOWED_ORIGINS=http://127.0.0.1:8000\n"
        "ITSM_TRUSTED_HOSTS=127.0.0.1,localhost\n"
        "ITSM_PORT=8000\n"
        "ITSM_HTTPS_PORT=443\n"
        "ITSM_ASSETPILOT_URL=http://127.0.0.1:5080\n"
        "ITSM_ASSETPILOT_PORT=5080\n"
        "ITSM_ASSETPILOT_INTERNAL_URL=http://127.0.0.1:5080\n",
        encoding="utf-8",
    )
    server_entry.configure_service_ports(
        tmp_path,
        8443,
        8011,
        5081,
        "helpdesk.example.test",
        "assets.example.test",
    )

    northstar = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ITSM_SECRET_KEY=keep-this-key" in northstar
    assert "ITSM_PUBLIC_URL=https://helpdesk.example.test:8443" in northstar
    assert "ITSM_ALLOWED_ORIGINS=https://helpdesk.example.test:8443" in northstar
    assert "ITSM_TRUSTED_HOSTS=helpdesk.example.test" in northstar
    assert "ITSM_ASSETPILOT_URL=http://127.0.0.1:5080" in northstar
    assert "ITSM_PUBLIC_URL=http://127.0.0.1" not in northstar
    caddy = (tmp_path / "Caddyfile").read_text(encoding="utf-8")
    assert "https://helpdesk.example.test:8443" in caddy
    assert "assets.example.test" not in caddy


def test_upgrade_wizard_rejects_legacy_loopback_hostnames():
    source = Path("installer/NorthstarDeskServer.iss").read_text(encoding="utf-8")
    assert "CompareText(Result, '127.0.0.1') = 0" in source
    assert "CompareText(Value, '127.0.0.1') <> 0" in source
    assert "(PageID = DnsPage.ID)" not in source
    assert "--dns-name" in source
    assert "--asset-dns-name" not in source


def test_server_installer_converts_evaluation_in_place():
    evaluation = Path("installer/NorthstarDesk.iss").read_text(encoding="utf-8")
    server = Path("installer/NorthstarDeskServer.iss").read_text(encoding="utf-8")
    product_id = "AppId={{B9890ED4-B32B-40E6-83D0-9A553FE65B4E}"
    assert product_id in evaluation
    assert product_id in server
    assert "CompareText(Trim(Lines[I]), 'ITSM_ENVIRONMENT=production') = 0" in server
    assert "Result := FileExists" not in server


def test_production_installer_uses_one_time_admin_password_file():
    source = Path("installer/NorthstarDeskServer.iss").read_text(encoding="utf-8")
    entry = Path("installer/server_entry.py").read_text(encoding="utf-8")

    assert "--initial-admin-password-file" in source
    assert "--initial-admin-password-file" in entry
    assert "InitialAdminPasswordFile" in source
    assert "DeleteFile(InitialAdminPasswordFile)" in source
    assert "admin / ChangeMe!2026" not in source


def test_final_server_installer_exists():
    if os.environ.get("NORTHSTAR_VERIFY_RELEASE_ARTIFACT") != "1":
        pytest.skip("release artifact verification runs only after the release gate builds it")
    package_source = Path("backend/itsm/__init__.py").read_text(encoding="utf-8")
    version_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)', package_source, re.MULTILINE)
    assert version_match, "backend package version is missing"
    setup = Path(f"installer/artifacts/NorthstarDesk-Server-Setup-{version_match.group(1)}.exe")
    assert setup.is_file()
    assert setup.stat().st_size > 1_000_000


def test_server_upgrade_is_backed_up_migrated_and_health_checked():
    script = Path("installer/NorthstarDeskServer.iss").read_text(encoding="utf-8")
    assert "backup --data-root" in script
    assert "migrate --data-root" in script
    assert "wait-ready --data-root" in script
    assert "HadConfiguration" in script
    assert "verified pre-upgrade database backup" in script
    assert "install-tasks.ps1" in script
    assert "run-caddy.cmd" in script
    assert "Network ports" in script
    assert "--https-port" in script
    assert "--northstar-port" in script
    assert "--assetpilot-port" not in script
    assert "configure-ports --data-root" in script
    assert "[Run]" not in script
    assert "services could not be installed or started" in script
    assert "services did not become ready" in script

    task_installer = Path("installer/install-tasks.ps1").read_text(encoding="utf-8")
    assert "-RestartCount 999" in task_installer
    assert 'UserId "SYSTEM"' in task_installer
    assert "Start-ScheduledTask" in task_installer


def test_server_installer_includes_migration_export_import_helpers():
    script = Path("installer/NorthstarDeskServer.iss").read_text(encoding="utf-8")
    entry = Path("installer/server_entry.py").read_text(encoding="utf-8")

    assert "export-migration.cmd" in script
    assert "import-migration.cmd" in script
    assert "export-migration" in entry
    assert "import-migration" in entry
    assert "--confirm must be exactly IMPORT" in entry
    assert "backup_existing_database(data_root)" in entry
    import_helper = Path("installer/import-migration.cmd").read_text(encoding="utf-8")
    assert 'install-tasks.ps1"' in import_helper
    assert "-InstallRoot" not in import_helper
