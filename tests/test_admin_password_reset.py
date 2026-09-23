from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import create_engine, text

from installer import admin_password_reset


def prepare_recovery_database(tmp_path: Path) -> Path:
    database = tmp_path / "recovery.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT, "
            "role TEXT, auth_source TEXT, password_hash TEXT, active BOOLEAN, "
            "must_change_password BOOLEAN, failed_attempts INTEGER, locked_until TEXT, "
            "updated_at TEXT)"
        ))
        connection.execute(text(
            "CREATE TABLE sessions (id INTEGER PRIMARY KEY, user_id INTEGER)"
        ))
        connection.execute(text(
            "INSERT INTO users VALUES (1, 'admin', 'admin@example.test', 'ADMIN', 'Local', "
            "'old-hash', false, true, 8, '2026-08-20', '2026-08-20')"
        ))
        connection.execute(text("INSERT INTO sessions VALUES (1, 1)"))
    engine.dispose()
    (tmp_path / ".env").write_text(
        f'ITSM_DATABASE_URL="sqlite:///{database.as_posix()}"\n', encoding="utf-8"
    )
    return database


def test_reset_local_admin_unlocks_account_and_revokes_sessions(tmp_path):
    database = prepare_recovery_database(tmp_path)
    admin_password_reset.reset_local_admin(tmp_path, "admin", "Recovered-Admin-2026!")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        account = connection.execute(text(
            "SELECT password_hash, active, must_change_password, failed_attempts, locked_until "
            "FROM users WHERE username='admin'"
        )).mappings().one()
        sessions = connection.execute(text("SELECT count(*) FROM sessions")).scalar_one()
    engine.dispose()
    assert PasswordHasher().verify(account["password_hash"], "Recovered-Admin-2026!")
    assert bool(account["active"]) is True
    assert bool(account["must_change_password"]) is False
    assert account["failed_attempts"] == 0
    assert account["locked_until"] is None
    assert sessions == 0


def test_reset_refuses_non_admin_account(tmp_path):
    database = prepare_recovery_database(tmp_path)
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET role='TECHNICIAN' WHERE username='admin'"))
    engine.dispose()
    try:
        admin_password_reset.reset_local_admin(tmp_path, "admin", "Recovered-Admin-2026!")
    except RuntimeError as exc:
        assert "not a Northstar administrator" in str(exc)
    else:
        raise AssertionError("Recovery must refuse non-administrator accounts")


def test_password_policy_matches_application_requirements():
    assert not admin_password_reset.password_errors("Recovered-Admin-2026!")
    assert admin_password_reset.password_errors("too-short")
