"""Production configuration and dependency checks for deployment automation."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from .config import settings
from .database import engine


PLACEHOLDER_SECRETS = {
    "development-only-change-this-secret-key",
    "replace-with-at-least-32-random-characters",
}


def evaluate() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not settings.production:
        errors.append("ITSM_ENVIRONMENT must be production")
    if not settings.database_url.startswith(("postgresql://", "postgresql+")):
        errors.append("Production requires PostgreSQL; ITSM_DATABASE_URL still selects SQLite")
    if len(settings.secret_key) < 32 or settings.secret_key in PLACEHOLDER_SECRETS:
        errors.append("ITSM_SECRET_KEY must be a unique random value of at least 32 characters")
    if not settings.cookie_secure:
        errors.append("ITSM_COOKIE_SECURE must be true")
    public = urlparse(settings.public_url)
    if public.scheme != "https" or not public.hostname:
        errors.append("ITSM_PUBLIC_URL must be the public HTTPS address")
    if not settings.origins or any(urlparse(origin).scheme != "https" for origin in settings.origins):
        errors.append("Every ITSM_ALLOWED_ORIGINS entry must use HTTPS")
    if not settings.hosts or "*" in settings.hosts or any(host in {"localhost", "127.0.0.1"} for host in settings.hosts):
        errors.append("ITSM_TRUSTED_HOSTS must contain the production DNS name and no wildcard")
    if public.hostname and public.hostname not in settings.hosts:
        errors.append("The ITSM_PUBLIC_URL hostname must be present in ITSM_TRUSTED_HOSTS")
    if settings.bind_host in {"0.0.0.0", "::"}:
        errors.append("ITSM_BIND_HOST must not expose Uvicorn directly; bind it to the reverse-proxy interface")
    if not Path("frontend/dist/index.html").is_file():
        errors.append("The frontend build is missing; run scripts\\build.cmd")

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current = inspect(connection).get_table_names()
            if "alembic_version" not in current:
                errors.append("Database has not been initialized with Alembic migrations")
            else:
                installed = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
                expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
                if installed != expected:
                    errors.append(f"Database migration is {installed or 'unknown'}; expected {expected}")
    except Exception as exc:
        errors.append(f"Database connectivity check failed ({type(exc).__name__})")

    backup_dir = Path(settings.backup_directory)
    if not backup_dir.is_dir():
        warnings.append(f"Backup directory does not exist: {backup_dir}")
    elif not any(backup_dir.glob("itsm-*")):
        warnings.append("No verified database backup was found")
    return errors, warnings


def main() -> int:
    errors, warnings = evaluate()
    print("Northstar Desk production readiness")
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARNING: {message}")
    if not errors and not warnings:
        print("PASS: configuration, database, migrations, and interface are ready")
    elif not errors:
        print("PASS WITH WARNINGS: required production checks passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
