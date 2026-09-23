"""User provisioning that is independent of inventory integrations."""
from __future__ import annotations

import hashlib
import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Role, User
from .security import hash_password


_SSO_ONLY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(48))


def normalized_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("A valid email address is required")
    return email


def _username_for_email(db: Session, email: str) -> str:
    local = re.sub(r"[^a-z0-9._-]+", ".", email.split("@", 1)[0]).strip("._-") or "user"
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:10]
    base = f"{local[:60]}-{digest}"[:80]
    candidate = base
    suffix = 1
    while db.scalar(select(User.id).where(func.lower(User.username) == candidate.lower())):
        suffix += 1
        marker = f"-{suffix}"
        candidate = f"{base[:80-len(marker)]}{marker}"
    return candidate


def provision_end_user(
    db: Session,
    *,
    organization_id: int,
    email: str,
    display_name: str = "",
    auth_source: str,
    role_source: str,
) -> tuple[User, bool]:
    """Find or create a least-privileged requester without inventory data."""
    email = normalized_email(email)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user:
        return user, False
    user = User(
        organization_id=organization_id,
        username=_username_for_email(db, email),
        email=email,
        display_name=display_name.strip() or email,
        password_hash=_SSO_ONLY_PASSWORD_HASH,
        role=Role.END_USER,
        active=True,
        must_change_password=False,
        auth_source=auth_source,
        role_source=role_source,
        team_source="Unassigned",
    )
    db.add(user)
    db.flush()
    return user, True
