r"""Opt-in PostgreSQL release gate for the packaged-server migration path.

These tests intentionally do not use the normal SQLite test fixture. They create
randomly named, disposable databases on an explicitly acknowledged ephemeral
PostgreSQL server and drop only those databases when the test finishes.

Run against a dedicated local/CI PostgreSQL instance, never production::

    $env:NORTHSTAR_POSTGRES_RELEASE_GATE = "EPHEMERAL_DATABASE_SERVER"
    $env:NORTHSTAR_POSTGRES_ADMIN_URL = `
      "postgresql+psycopg://postgres:password@127.0.0.1:5432/postgres"
    .\.venv\Scripts\python.exe -m pytest -q tests\test_postgresql_release_gate.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACKNOWLEDGEMENT = "EPHEMERAL_DATABASE_SERVER"
DATABASE_PREFIX = "northstar_release_gate_"


def _admin_url() -> URL:
    if os.environ.get("NORTHSTAR_POSTGRES_RELEASE_GATE") != ACKNOWLEDGEMENT:
        pytest.skip(
            "PostgreSQL release gate is disabled; use a dedicated ephemeral "
            "server and set NORTHSTAR_POSTGRES_RELEASE_GATE explicitly."
        )
    raw_url = os.environ.get("NORTHSTAR_POSTGRES_ADMIN_URL", "").strip()
    if not raw_url:
        pytest.fail("NORTHSTAR_POSTGRES_ADMIN_URL is required for the PostgreSQL release gate")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("The release gate administrator URL must select PostgreSQL")
    if url.database not in {"postgres", "template1"}:
        pytest.fail(
            "The administrator URL must connect to postgres or template1, never an application database"
        )
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _database_url(admin_url: URL, database_name: str) -> str:
    return admin_url.set(database=database_name).render_as_string(hide_password=False)


@pytest.fixture
def disposable_database():
    """Create only UUID-named gate databases and always attempt to remove them."""

    admin_url = _admin_url()
    engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    created: list[str] = []

    def create(label: str) -> str:
        safe_label = "".join(character for character in label.lower() if character.isalnum())[:12]
        # Keep the generated identifier below PostgreSQL's 63-byte limit.
        database_name = f"{DATABASE_PREFIX}{safe_label}_{uuid.uuid4().hex[:16]}"
        assert database_name.startswith(DATABASE_PREFIX)
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        created.append(database_name)
        return _database_url(admin_url, database_name)

    try:
        yield create
    finally:
        with engine.connect() as connection:
            for database_name in reversed(created):
                if not database_name.startswith(DATABASE_PREFIX):
                    raise AssertionError("Refusing to drop a database outside the release-gate namespace")
                connection.execute(
                    sa.text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                    ),
                    {"database_name": database_name},
                )
                connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
        engine.dispose()


def _child_environment(database_url: str, data_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(PROJECT_ROOT / "backend"),
            "ITSM_DATABASE_URL": database_url,
            "ITSM_ENVIRONMENT": "production",
            "ITSM_SECRET_KEY": "release-gate-only-secret-key-that-is-long-enough",
            "ITSM_COOKIE_SECURE": "true",
            "ITSM_PUBLIC_URL": "https://release-gate.invalid",
            "ITSM_ALLOWED_ORIGINS": "https://release-gate.invalid",
            "ITSM_TRUSTED_HOSTS": "release-gate.invalid",
            "ITSM_DATA_DIRECTORY": str(data_root / "data"),
            "ITSM_BACKUP_DIRECTORY": str(data_root / "backups"),
            "ITSM_OUTBOUND_EMAIL_ENABLED": "false",
        }
    )
    return environment


def _run_alembic(database_url: str, data_root: Path, revision: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(PROJECT_ROOT / "alembic.ini"), "upgrade", revision],
        cwd=PROJECT_ROOT,
        env=_child_environment(database_url, data_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def _run_alembic_downgrade(database_url: str, data_root: Path, revision: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(PROJECT_ROOT / "alembic.ini"), "downgrade", revision],
        cwd=PROJECT_ROOT,
        env=_child_environment(database_url, data_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def _run_server_initialize(database_url: str, data_root: Path) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    # Keep a realistic packaged-server configuration file as well as explicit
    # child-process variables. Explicit variables prevent the normal test
    # suite's SQLite setting from leaking into this process.
    (data_root / ".env").write_text(
        "\n".join(
            [
                "ITSM_ENVIRONMENT=production",
                f"ITSM_DATABASE_URL={json.dumps(database_url)}",
                "ITSM_SECRET_KEY=release-gate-only-secret-key-that-is-long-enough",
                "ITSM_COOKIE_SECURE=true",
                "ITSM_PUBLIC_URL=https://release-gate.invalid",
                "ITSM_ALLOWED_ORIGINS=https://release-gate.invalid",
                "ITSM_TRUSTED_HOSTS=release-gate.invalid",
                "ITSM_OUTBOUND_EMAIL_ENABLED=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script = (
        "from pathlib import Path; "
        "from installer.server_entry import initialize; "
        "initialize(Path(__import__('sys').argv[1]), 'Release Gate', "
        "'admin@release-gate.invalid', 'Release-Gate-Admin-2026!')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(data_root)],
        cwd=PROJECT_ROOT,
        env=_child_environment(database_url, data_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def _expected_head() -> str:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def _assert_head_and_capacity(database_url: str) -> None:
    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            installed = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
            width = connection.execute(
                sa.text(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'alembic_version' AND column_name = 'version_num'"
                )
            ).scalar_one()
            tables = set(sa.inspect(connection).get_table_names())
        assert installed == _expected_head()
        assert width is not None and width >= 128
        assert {
            "organizations",
            "users",
            "tickets",
            "config_items",
            "endpoint_agents",
            "telephony_calls",
            "system_updates",
        }.issubset(tables)
    finally:
        engine.dispose()


def _row_counts(database_url: str) -> dict[str, int]:
    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return {
                table: connection.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
                for table in ("organizations", "users", "tickets", "config_items")
            }
    finally:
        engine.dispose()


def test_fresh_postgresql_initialize_reaches_head_and_is_idempotent(
    disposable_database, tmp_path: Path
):
    database_url = disposable_database("fresh")
    data_root = tmp_path / "fresh-server-data"

    _run_server_initialize(database_url, data_root)
    _assert_head_and_capacity(database_url)
    first_counts = _row_counts(database_url)
    assert first_counts["organizations"] == 1
    assert first_counts["users"] == 1
    assert first_counts["tickets"] == 0
    assert first_counts["config_items"] > 0

    _run_server_initialize(database_url, data_root)
    _assert_head_and_capacity(database_url)
    assert _row_counts(database_url) == first_counts


def test_legacy_0009_varchar32_resume_reaches_head_and_is_idempotent(
    disposable_database, tmp_path: Path
):
    database_url = disposable_database("resume0009")
    data_root = tmp_path / "resume-server-data"

    _run_alembic(database_url, data_root, "0009_administration_foundation")
    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "0009_administration_foundation"
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE alembic_version "
                    "ALTER COLUMN version_num TYPE VARCHAR(32)"
                )
            )
    finally:
        engine.dispose()

    # The child invokes packaged-server initialize(), which must repair the
    # tracking column before Alembic attempts to record revision 0010.
    _run_server_initialize(database_url, data_root)
    _assert_head_and_capacity(database_url)
    first_counts = _row_counts(database_url)
    assert first_counts["organizations"] == 1
    assert first_counts["users"] == 1
    assert first_counts["tickets"] == 0
    assert first_counts["config_items"] > 0

    _run_server_initialize(database_url, data_root)
    _assert_head_and_capacity(database_url)
    assert _row_counts(database_url) == first_counts


def test_real_0020_to_head_upgrade_preserves_messages_and_builds_chat_schema(
    disposable_database, tmp_path: Path
):
    """Exercise the exact packaged upgrade path used by version 0.4.8."""
    database_url = disposable_database("upgrade0020")
    data_root = tmp_path / "upgrade-0020-data"
    # Build today's complete schema first, then use the real 0021 downgrade to
    # obtain an authentic 0.4.8/0020 database. Starting a fresh database at
    # 0020 is invalid because revision 0001 deliberately creates current
    # metadata and would make 0021 a no-op.
    _run_server_initialize(database_url, data_root)
    _run_alembic_downgrade(database_url, data_root, "0020_signed_system_updates")

    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            organization_id = connection.execute(sa.text(
                "SELECT id FROM organizations ORDER BY id LIMIT 1"
            )).scalar_one()
            user_id = connection.execute(sa.text(
                "SELECT id FROM users WHERE organization_id = :organization_id ORDER BY id LIMIT 1"
            ), {"organization_id": organization_id}).scalar_one()
            team_id = connection.execute(sa.text(
                "SELECT id FROM teams WHERE organization_id = :organization_id ORDER BY id LIMIT 1"
            ), {"organization_id": organization_id}).scalar_one()
            ticket_id = connection.execute(sa.text(
                "INSERT INTO tickets (organization_id, number, request_type, subject, description, "
                "requester_id, team_id, status, priority, impact, urgency, mode, level, impact_details, "
                "site_location, emails_to_notify, calculated_priority, priority_source, category, "
                "next_action_owner, next_action, first_response_due, resolution_due, restricted, reopened_count, "
                "route_reason, routing_trace, sla_policy_key, sla_explanation, custom_data, requester_snapshot, "
                "created_at, updated_at) "
                "VALUES (:organization_id, 'REQ-UPGRADE', 'Report an issue', 'Upgrade test', "
                "'Preserve this ticket', :user_id, :team_id, 'NEW', 'Medium', 'Medium', 'Medium', "
                "'Web Form', 'Tier 1', '', '', '[]'::json, 'Medium', 'calculated', 'General', "
                "'IT', 'Initial triage', CURRENT_TIMESTAMP + INTERVAL '1 hour', "
                "CURRENT_TIMESTAMP + INTERVAL '8 hours', false, 0, 'Default queue fallback', '[]'::json, "
                "'', '', '{}'::json, '{}'::json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
                "RETURNING id"
            ), {"organization_id": organization_id, "user_id": user_id, "team_id": team_id}).scalar_one()
            connection.execute(sa.text(
                "INSERT INTO ticket_messages (ticket_id, author_id, body, kind, source, created_at) "
                "VALUES (:ticket_id, :user_id, 'Preserve this message', 'public', 'web', CURRENT_TIMESTAMP)"
            ), {"ticket_id": ticket_id, "user_id": user_id})
    finally:
        engine.dispose()

    _run_alembic(database_url, data_root, "head")
    _run_alembic(database_url, data_root, "head")

    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            inspector = sa.inspect(connection)
            columns = {item["name"] for item in inspector.get_columns("ticket_messages")}
            foreign_keys = inspector.get_foreign_keys("ticket_messages")
            unique_constraints = {item["name"] for item in inspector.get_unique_constraints("ticket_messages")}
            indexes = {item["name"] for item in inspector.get_indexes("ticket_messages")}
            table_names = inspector.get_table_names()
            preserved = connection.execute(sa.text(
                "SELECT body FROM ticket_messages WHERE body = 'Preserve this message'"
            )).scalar_one()
        assert preserved == "Preserve this message"
        assert {"chat_session_id", "client_message_id"}.issubset(columns)
        assert "ticket_chat_sessions" in table_names
        assert any(item.get("referred_table") == "ticket_chat_sessions" and
                   item.get("constrained_columns") == ["chat_session_id"] for item in foreign_keys)
        assert "uq_ticket_message_chat_client" in unique_constraints
        assert "ix_ticket_messages_chat_session_id" in indexes
    finally:
        engine.dispose()
    _assert_head_and_capacity(database_url)
