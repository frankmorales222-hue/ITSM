import importlib

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from itsm.database import Base
from itsm.models import (
    Announcement,
    Asset,
    AutomationFailure,
    ConfigItem,
    Employee,
    Organization,
    Role,
    RoleDefinition,
    SupportQueue,
    Team,
    Ticket,
    User,
)
from itsm.security import verify_password


@pytest.fixture()
def production_seed_database(tmp_path, monkeypatch):
    seed_module = importlib.import_module("itsm.seed")
    engine = create_engine(f"sqlite:///{tmp_path / 'production-seed.db'}")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(seed_module, "engine", engine)
    monkeypatch.setattr(seed_module, "SessionLocal", session_factory)
    yield seed_module, session_factory
    engine.dispose()


def test_production_seed_creates_one_supplied_admin_and_no_demo_data(
    production_seed_database,
):
    seed_module, session_factory = production_seed_database
    password = "Unique-Production-Admin-2026!"

    seed_module.seed_production(
        "Example Support", "OWNER@EXAMPLE.COM", password,
    )
    # Normal service startup is allowed to call initialization again without
    # having access to the one-time installer password.
    seed_module.seed_production()

    with session_factory() as db:
        users = db.scalars(select(User)).all()
        assert len(users) == 1
        assert users[0].username == "admin"
        assert users[0].email == "owner@example.com"
        assert users[0].role == Role.ADMIN
        assert users[0].must_change_password is False
        assert verify_password(users[0].password_hash, password)
        assert db.scalar(select(Organization.name)) == "Example Support"
        assert db.scalar(select(func.count()).select_from(RoleDefinition)) == 6
        assert db.scalar(select(func.count()).select_from(Team)) == 1
        assert db.scalar(select(func.count()).select_from(SupportQueue)) == 1
        assert db.scalar(select(func.count()).select_from(ConfigItem)) >= 10
        for model in (Employee, Asset, Ticket, Announcement, AutomationFailure):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_production_seed_rejects_weak_password_without_writing_data(
    production_seed_database,
):
    seed_module, session_factory = production_seed_database

    with pytest.raises(ValueError, match="Initial administrator password"):
        seed_module.seed_production("Example Support", "owner@example.com", "weak")

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(Organization)) == 0


def test_production_seed_refuses_database_with_demo_or_multiple_users(
    production_seed_database,
):
    seed_module, session_factory = production_seed_database
    Base.metadata.create_all(seed_module.engine)
    with session_factory() as db:
        organization = Organization(name="Existing", slug="primary")
        db.add(organization)
        db.flush()
        db.info["organization_id"] = organization.id
        db.add(User(
            username="user1", email="user1@example.test", display_name="Demo User",
            password_hash="not-a-real-hash", role=Role.END_USER,
        ))
        db.commit()

    with pytest.raises(RuntimeError, match="already contains users"):
        seed_module.seed_production(
            "Example Support", "owner@example.com", "Unique-Production-Admin-2026!",
        )


def test_populated_database_migration_startup_does_not_reseed_or_refuse(
    production_seed_database,
):
    """An upgrade invokes seed_production without bootstrap credentials."""
    seed_module, session_factory = production_seed_database
    Base.metadata.create_all(seed_module.engine)
    with session_factory() as db:
        organization = Organization(name="Existing Production", slug="primary")
        db.add(organization)
        db.flush()
        db.info["organization_id"] = organization.id
        db.add(User(
            username="existing-user", email="existing@example.test",
            display_name="Existing User", password_hash="preserved-hash",
            role=Role.END_USER,
        ))
        db.commit()

    seed_module.seed_production()

    with session_factory() as db:
        users = db.scalars(select(User)).all()
        assert len(users) == 1
        assert users[0].username == "existing-user"
        assert users[0].password_hash == "preserved-hash"
