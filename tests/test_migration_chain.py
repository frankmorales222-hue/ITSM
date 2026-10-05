from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from itsm.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def current_revision(database_url: str) -> str:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


def test_alembic_has_exactly_one_head():
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    heads = script.get_heads()
    assert heads == ["0013_agent_health_state"]


def test_real_alembic_chain_upgrades_fresh_sqlite_database(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)
    command.upgrade(alembic_config(database_url), "head")
    assert current_revision(database_url) == "0013_agent_health_state"


def test_real_alembic_chain_upgrades_from_0024_to_head(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'from-0024.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = alembic_config(database_url)
    command.upgrade(config, "0024_endpoint_action_auto")
    assert current_revision(database_url) == "0024_endpoint_action_auto"
    command.upgrade(config, "head")
    assert current_revision(database_url) == "0013_agent_health_state"
