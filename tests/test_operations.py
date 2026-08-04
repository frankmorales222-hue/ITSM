import sqlite3
import shutil
import uuid
from pathlib import Path

import pytest

from itsm.database_ops import create_backup, restore_backup, verify_backup


@pytest.fixture()
def operation_dir():
    path = Path("data/test-operations") / uuid.uuid4().hex
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_sqlite_backup_is_created_and_verified(operation_dir):
    source = operation_dir / "source.sqlite"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO sample(value) VALUES ('preserved')")
    connection.commit()
    connection.close()

    backup = create_backup(f"sqlite:///{source.as_posix()}", operation_dir / "backups")
    verify_backup(backup)
    restored = sqlite3.connect(backup)
    assert restored.execute("SELECT value FROM sample").fetchone()[0] == "preserved"
    restored.close()
    assert backup.with_suffix(".sqlite.sha256").is_file()

    restore_target = operation_dir / "restored.sqlite"
    restore_backup(backup, f"sqlite:///{restore_target.as_posix()}")
    restored = sqlite3.connect(restore_target)
    assert restored.execute("SELECT value FROM sample").fetchone()[0] == "preserved"
    restored.close()


def test_backup_verification_rejects_checksum_mismatch(operation_dir):
    source = operation_dir / "source.sqlite"
    sqlite3.connect(source).close()
    backup = create_backup(f"sqlite:///{source.as_posix()}", operation_dir / "backups")
    backup.with_suffix(".sqlite.sha256").write_text("0" * 64 + "  wrong.sqlite\n")
    with pytest.raises(RuntimeError, match="checksum"):
        verify_backup(backup)


def test_readiness_probe_checks_database(client):
    result = client.get("/api/health/ready")
    assert result.status_code == 200
    assert result.json()["status"] == "ready"
