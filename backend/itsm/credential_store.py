"""Encrypted organization integration credentials."""
import base64
import hashlib

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import IntegrationSecret


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def set_integration_secret(db: Session, provider: str, name: str, value: str) -> None:
    record = db.scalar(select(IntegrationSecret).where(
        IntegrationSecret.provider == provider, IntegrationSecret.name == name))
    if not record:
        record = IntegrationSecret(provider=provider, name=name, encrypted_value="")
        db.add(record)
    record.encrypted_value = _cipher().encrypt(value.encode()).decode()


def clear_integration_secret(db: Session, provider: str, name: str) -> None:
    record = db.scalar(select(IntegrationSecret).where(
        IntegrationSecret.provider == provider, IntegrationSecret.name == name))
    if record:
        db.delete(record)


def integration_secret_status(db: Session, provider: str) -> dict[str, bool]:
    names = db.scalars(select(IntegrationSecret.name).where(IntegrationSecret.provider == provider)).all()
    return {name: True for name in names}
