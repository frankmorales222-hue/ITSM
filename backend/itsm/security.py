import hashlib
import re
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .database import get_db
from .models import Role, Session, User, now

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def validate_password(password: str) -> list[str]:
    errors = []
    if len(password) < 12: errors.append("Use at least 12 characters")
    if not re.search(r"[A-Z]", password): errors.append("Add an uppercase letter")
    if not re.search(r"[a-z]", password): errors.append("Add a lowercase letter")
    if not re.search(r"\d", password): errors.append("Add a number")
    if not re.search(r"[^A-Za-z0-9]", password): errors.append("Add a symbol")
    return errors


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return ph.verify(stored, password)
    except VerifyMismatchError:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: DBSession, user: User) -> tuple[str, str, Session]:
    raw = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    session = Session(token_hash=token_hash(raw), csrf_token=csrf, user_id=user.id,
                      expires_at=now() + timedelta(minutes=settings.session_minutes))
    db.add(session)
    db.flush()
    return raw, csrf, session


def get_current_session(request: Request, db: DBSession = Depends(get_db)) -> Session:
    raw = request.cookies.get("itsm_session")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session = db.scalar(select(Session).where(Session.token_hash == token_hash(raw)))
    expiry = session.expires_at.replace(tzinfo=session.expires_at.tzinfo or now().tzinfo) if session else None
    if not session or expiry <= now() or not session.user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    db.info["organization_id"] = session.user.organization_id
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("X-CSRF-Token") != session.csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return session


def current_user(session: Session = Depends(get_current_session)) -> User:
    return session.user


def require_roles(*roles: Role):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action")
        return user
    return dependency


STAFF_ROLES = (Role.TECHNICIAN, Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN)
REPORT_ROLES = (Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN, Role.AUDITOR)
