from sqlalchemy import select

from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import Notification, Ticket, TicketStatus


CHANGE_FORM = {
    "name": "Production Change",
    "slug": "production-change",
    "description": "Controlled production change",
    "category": "Change",
    "icon": "change",
    "active": True,
    "published": True,
    "fields": [
        {"id": "reason", "key": "reason", "label": "Business reason", "type": "long_text",
         "required": True, "help": "", "options": []},
        {"id": "risk", "key": "risk", "label": "Risk", "type": "select",
         "required": True, "help": "", "options": ["Low", "High"]},
    ],
}


def test_custom_form_approval_and_email_outbox(admin, client):
    created = admin.post("/api/admin/forms", json=CHANGE_FORM)
    assert created.status_code == 201, created.text
    form = created.json()
    workflow = admin.post("/api/admin/approval-workflows", json={
        "name": "Production approval", "form_definition_id": form["id"], "active": True,
        "steps": [{"name": "IT manager approval", "approver_role": "manager", "approver_user_id": None}],
    })
    assert workflow.status_code == 201, workflow.text

    submitted = admin.post(f"/api/forms/{form['id']}/submit", json={
        "subject": "Deploy release 4.2", "values": {"reason": "Security maintenance", "risk": "Low"},
        "impact": "Medium", "urgency": "Medium",
    })
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["approval_required"] is True
    ticket = submitted.json()["ticket"]
    assert ticket["number"].startswith("CHG-")
    assert ticket["status"] == "Waiting on Approval"
    assert ticket["custom_data"]["risk"] == "Low"

    with SessionLocal() as db:
        stored = db.get(Ticket, ticket["id"])
        assert stored.status == TicketStatus.WAITING_APPROVAL
        approval_email = db.scalar(select(Notification).where(
            Notification.ticket_id == ticket["id"], Notification.event == "approval.requested"))
        assert approval_email.delivery_status == "pending_email"

    manager_csrf = login_as(client, "manager")
    client.headers.update({"X-CSRF-Token": manager_csrf})
    queue = client.get("/api/approvals")
    assert queue.status_code == 200
    approval = next(item for item in queue.json() if item["ticket_id"] == ticket["id"])
    decision = client.post(f"/api/approvals/{approval['id']}/decision", json={
        "decision": "Approved", "comment": "Approved for the maintenance window",
    })
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "Approved"
    assert client.get(f"/api/tickets/{ticket['id']}").json()["status"] in {"New", "Assigned"}


def test_form_rejects_invalid_option(admin):
    created = admin.post("/api/admin/forms", json={**CHANGE_FORM, "name": "Validated Change", "slug": "validated-change"})
    form_id = created.json()["id"]
    result = admin.post(f"/api/forms/{form_id}/submit", json={
        "subject": "Invalid risk selection", "values": {"reason": "Test validation", "risk": "Impossible"},
    })
    assert result.status_code == 422
    assert "invalid option" in result.text


def test_saved_custom_report_executes_authorized_columns(admin):
    created = admin.post("/api/admin/report-definitions", json={
        "name": "Change queue report", "description": "Saved change workload",
        "configuration": {
            "columns": ["number", "subject", "status", "request_type"],
            "filters": [{"field": "request_type", "operator": "contains", "value": "Change"}],
            "group_by": "status",
        },
        "active": True,
    })
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]
    result = admin.get(f"/api/reports/{report_id}/run")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["columns"] == ["number", "subject", "status", "request_type"]
    assert all("Change" in row["request_type"] for row in body["rows"])
