from sqlalchemy import select

from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import Employee, Notification, Organization, PasswordResetToken, User
from itsm.security import verify_password


def test_technician_lookup_materializes_asset_inventory_employee(client):
    with SessionLocal() as db:
        organization_id = db.scalar(select(Organization.id))
        employee = Employee(organization_id=organization_id, employee_number="AP-FIRST-LOGIN",
                            first_name="Avery", last_name="Inventory", preferred_name="Avery",
                            work_email="avery.inventory@example.com", job_title="Analyst",
                            employment_status="Active", source="AssetPilot")
        db.add(employee); db.commit()
    csrf = login_as(client, "tech1"); client.headers.update({"X-CSRF-Token": csrf})
    result = client.get("/api/lookups/users?q=avery.inventory@example.com")
    assert result.status_code == 200, result.text
    profile = next(item for item in result.json() if item["email"] == "avery.inventory@example.com")
    with SessionLocal() as db:
        user = db.get(User, profile["id"])
        employee = db.scalar(select(Employee).where(Employee.work_email == "avery.inventory@example.com"))
        assert user and user.auth_source == "AssetPilot" and user.must_change_password
        assert employee.user_id == user.id


def test_first_time_user_can_request_and_complete_password_setup(client, monkeypatch):
    from itsm import main as main_module

    token = "first-time-secure-token-abcdefghijklmnopqrstuvwxyz-1234567890"
    monkeypatch.setattr(main_module.secrets, "token_urlsafe", lambda _length: token)
    requested = client.post("/api/auth/forgot-password", json={"email": "avery.inventory@example.com"})
    assert requested.status_code == 200
    assert "If that email" in requested.json()["message"]
    with SessionLocal() as db:
        account = db.scalar(select(User).where(User.email == "avery.inventory@example.com"))
        assert db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == account.id))
        notice = db.scalar(select(Notification).where(Notification.user_id == account.id,
                                                       Notification.event == "password.reset_requested"))
        assert token in notice.body and notice.delivery_status == "pending_email"
    completed = client.post("/api/auth/reset-password", json={"token": token, "new_password": "AverySecure!2026"})
    assert completed.status_code == 200, completed.text
    with SessionLocal() as db:
        account = db.scalar(select(User).where(User.email == "avery.inventory@example.com"))
        assert verify_password(account.password_hash, "AverySecure!2026")
        assert account.must_change_password is False
    login = client.post("/api/auth/login", json={"username": "avery.inventory@example.com", "password": "AverySecure!2026"})
    assert login.status_code == 200, login.text


def test_forgot_password_does_not_disclose_unknown_accounts(client):
    result = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert result.status_code == 200
    assert "If that email" in result.json()["message"]
