from conftest import login_as
from sqlalchemy import select
from itsm.database import SessionLocal
from itsm.models import Employee, User


def test_user_can_update_own_profile_and_restore_it(client):
    csrf = login_as(client, "user1")
    client.headers.update({"X-CSRF-Token": csrf})
    original = client.get("/api/auth/me").json()["user"]
    changed = client.patch("/api/auth/profile", json={
        "display_name": "Updated Requester",
        "email": "updated.requester@example.com",
        "phone": "+1 555 010 2222",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["display_name"] == "Updated Requester"
    assert changed.json()["phone"] == "+1 555 010 2222"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "user1"))
        user.display_name = original["display_name"]
        user.email = original["email"]
        user.phone = original.get("phone", "")
        employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
        if employee:
            employee.work_email = original["email"]
        db.commit()


def test_custom_report_supports_subject_team_status_and_date_fields(admin):
    created = admin.post("/api/admin/report-definitions", json={
        "name": "Flexible ticket search",
        "description": "No hard-coded ticket topic",
        "active": True,
        "configuration": {
            "columns": ["number", "subject", "description", "status", "team", "requester_department", "created_at"],
            "filters": [
                {"field": "subject", "operator": "contains", "value": "test"},
                {"field": "team", "operator": "not_equals", "value": ""},
                {"field": "created_at", "operator": "after", "value": "2020-01-01"},
            ],
            "group_by": "team",
        },
    })
    assert created.status_code == 201, created.text
    result = admin.get(f"/api/reports/{created.json()['id']}/run")
    assert result.status_code == 200, result.text
    assert result.json()["columns"] == ["number", "subject", "description", "status", "team", "requester_department", "created_at"]


def test_hard_coded_password_reset_report_is_removed(admin):
    assert admin.get("/api/reports/password-resets.csv").status_code == 404
