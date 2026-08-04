from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import AuditEvent, User
from sqlalchemy import select


def test_login_session_and_logout(client):
    csrf=login_as(client,"manager")
    assert client.get("/api/auth/me").json()["user"]["role"]=="manager"
    response=client.post("/api/auth/logout",headers={"X-CSRF-Token":csrf})
    assert response.status_code==200
    assert client.get("/api/auth/me").status_code==401


def test_failed_login_and_lockout(client):
    for _ in range(5): client.post("/api/auth/login",json={"username":"user5","password":"wrong"})
    locked=client.post("/api/auth/login",json={"username":"user5","password":"ChangeMe!2026"})
    assert locked.status_code==423
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username=="user5"));user.failed_attempts=0;user.locked_until=None;db.commit()
        assert db.scalar(select(AuditEvent).where(AuditEvent.action=="login.failed"))


def test_password_policy_and_change(client):
    csrf=login_as(client,"user4")
    weak=client.post("/api/auth/change-password",headers={"X-CSRF-Token":csrf},json={"current_password":"ChangeMe!2026","new_password":"weak"})
    assert weak.status_code==422
    okay=client.post("/api/auth/change-password",headers={"X-CSRF-Token":csrf},json={"current_password":"ChangeMe!2026","new_password":"A-Strong-Pass-2026!"})
    assert okay.status_code==200


def test_csrf_required(client):
    login_as(client,"tech1")
    assert client.post("/api/auth/logout").status_code==403

