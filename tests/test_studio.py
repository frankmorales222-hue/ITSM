import runpy
from pathlib import Path

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


def test_reusable_tasks_activate_after_approval_and_block_closure(admin, client):
    task=admin.post("/api/admin/task-templates",json={"name":"Approved change implementation","description":"Safe delivery checklist","active":True,"items":[
        {"id":"backup","label":"Confirm backup","required":True},{"id":"validate","label":"Validate service","required":True}]})
    assert task.status_code==201,task.text
    form=admin.post("/api/admin/forms",json={**CHANGE_FORM,"name":"Task controlled change","slug":"task-controlled-change"})
    assert form.status_code==201,form.text
    workflow=admin.post("/api/admin/approval-workflows",json={"name":"Task controlled approval","form_definition_id":form.json()["id"],"active":True,
        "steps":[{"name":"Manager approval","approver_role":"manager","approver_user_id":None}],"task_template_ids":[task.json()["id"]],
        "closure_requirements":{"require_resolution_summary":True,"require_checklists":True}})
    assert workflow.status_code==201,workflow.text
    submitted=admin.post(f"/api/forms/{form.json()['id']}/submit",json={"subject":"Controlled task execution","values":{"reason":"Maintenance","risk":"Low"}})
    assert submitted.status_code==201,submitted.text;ticket=submitted.json()["ticket"]
    detail=admin.get(f"/api/tickets/{ticket['id']}").json();assert detail["checklists"][0]["status"]=="Blocked"

    manager_csrf=login_as(client,"manager");client.headers.update({"X-CSRF-Token":manager_csrf})
    approval=next(item for item in client.get("/api/approvals").json() if item["ticket_id"]==ticket["id"])
    assert client.post(f"/api/approvals/{approval['id']}/decision",json={"decision":"Approved","comment":"Proceed"}).status_code==200
    detail=client.get(f"/api/tickets/{ticket['id']}").json();checklist=detail["checklists"][0];assert checklist["status"]=="Active"
    blocked=client.patch(f"/api/tickets/{ticket['id']}",json={"resolution_summary":"Implemented","status":"Resolved"})
    assert blocked.status_code==422 and "checklists" in blocked.text
    for row in checklist["items"]:
        result=client.patch(f"/api/tickets/{ticket['id']}/checklists/{checklist['id']}",json={"item_id":row["id"],"completed":True,"note":"Verified"})
        assert result.status_code==200,result.text
    resolved=client.patch(f"/api/tickets/{ticket['id']}",json={"resolution_summary":"Implemented and validated","status":"Resolved"})
    assert resolved.status_code==200,resolved.text
    assert resolved.json()["status"]=="Resolved"


def test_form_rejects_invalid_option(admin):
    created = admin.post("/api/admin/forms", json={**CHANGE_FORM, "name": "Validated Change", "slug": "validated-change"})
    form_id = created.json()["id"]
    result = admin.post(f"/api/forms/{form_id}/submit", json={
        "subject": "Invalid risk selection", "values": {"reason": "Test validation", "risk": "Impossible"},
    })
    assert result.status_code == 422
    assert "invalid option" in result.text


def test_form_preserves_visual_layout_and_validates_card_choices(admin):
    payload = {**CHANGE_FORM, "name": "Visual request", "slug": "visual-request"}
    payload["fields"] = [
        {"id": "request", "key": "request_category", "label": "Request category",
         "type": "choice_cards", "required": True, "help": "Choose the closest match",
         "options": ["Hardware", "Software", "Access"], "width": "full",
         "placeholder": "Choose a category", "icon": "grid"},
        {"id": "phone", "key": "phone", "label": "Phone number", "type": "phone",
         "required": False, "help": "", "options": [], "width": "half",
         "placeholder": "(555) 123-4567", "icon": "phone", "max_length": 25},
    ]
    created = admin.post("/api/admin/forms", json=payload)
    assert created.status_code == 201, created.text
    fields = created.json()["fields"]
    assert fields[0]["type"] == "choice_cards"
    assert fields[0]["width"] == "full"
    assert fields[1]["placeholder"] == "(555) 123-4567"
    assert fields[1]["max_length"] == 25

    bad = admin.post(f"/api/forms/{created.json()['id']}/submit", json={
        "subject": "Need some help", "values": {"request_category": "Something else"},
    })
    assert bad.status_code == 422
    assert "invalid option" in bad.text

    too_long = admin.post(f"/api/forms/{created.json()['id']}/submit", json={
        "subject": "Phone input limit", "values": {"request_category": "Hardware", "phone": "1" * 26},
    })
    assert too_long.status_code == 422
    assert "25 characters or fewer" in too_long.text


def test_conditional_fields_only_validate_when_visible(admin):
    payload = {**CHANGE_FORM, "name": "Dynamic Request", "slug": "dynamic-request"}
    payload["fields"] = [
        {"id": "type", "key": "request_kind", "label": "Request kind", "type": "select",
         "required": True, "help": "", "options": ["Hardware", "Software"]},
        {"id": "hardware", "key": "hardware_problem", "label": "Hardware problem", "type": "short_text",
         "required": True, "help": "", "options": [], "show_when": {"key": "request_kind", "value": "Hardware"}},
        {"id": "internal", "key": "internal_value", "label": "Internal", "type": "short_text",
         "required": True, "help": "", "options": [], "visibility": "hidden"},
    ]
    created = admin.post("/api/admin/forms", json=payload)
    assert created.status_code == 201, created.text
    fields = created.json()["fields"]
    assert fields[1]["show_when"] == {"key": "request_kind", "value": "Hardware"}
    assert fields[2]["visibility"] == "hidden"
    software = admin.post(f"/api/forms/{created.json()['id']}/submit", json={
        "subject": "Software request test", "values": {"request_kind": "Software"},
    })
    assert software.status_code == 201, software.text
    hardware = admin.post(f"/api/forms/{created.json()['id']}/submit", json={
        "subject": "Hardware request test", "values": {"request_kind": "Hardware"},
    })
    assert hardware.status_code == 422
    assert "Hardware problem is required" in hardware.text


def test_form_layouts_defaults_technician_fields_and_conditional_required(admin):
    payload = {**CHANGE_FORM, "name": "Role aware request", "slug": "role-aware-request"}
    payload["fields"] = [
        {"id": "kind", "key": "kind", "label": "Kind", "type": "select", "required": True,
         "help": "", "options": ["Normal", "Emergency"]},
        {"id": "code", "key": "code", "label": "Emergency code", "type": "short_text", "required": False,
         "help": "", "options": [], "required_when": {"key": "kind", "value": "Emergency"}},
        {"id": "source", "key": "source", "label": "Source", "type": "short_text", "required": False,
         "help": "", "options": [], "default_value": "Portal", "read_only": True},
        {"id": "triage", "key": "triage", "label": "Triage notes", "type": "long_text", "required": True,
         "help": "", "options": [], "visibility": "technician_only"},
    ]
    payload["requester_layout"] = ["kind", "code", "source", "triage"]
    payload["technician_layout"] = ["triage", "kind", "code", "source"]
    created = admin.post("/api/admin/forms", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["technician_layout"][0] == "triage"
    assert body["fields"][2]["default_value"] == "Portal"

    normal = admin.post(f"/api/forms/{body['id']}/submit", json={
        "subject": "Normal role aware request", "values": {"kind": "Normal"},
    })
    assert normal.status_code == 201, normal.text
    assert normal.json()["ticket"]["custom_data"]["source"] == "Portal"
    assert "triage" not in normal.json()["ticket"]["custom_data"]

    emergency = admin.post(f"/api/forms/{body['id']}/submit", json={
        "subject": "Emergency request test", "values": {"kind": "Emergency"},
    })
    assert emergency.status_code == 422
    assert "Emergency code is required" in emergency.text


def test_form_layout_validation_version_restore_archive_and_unarchive(admin):
    payload = {**CHANGE_FORM, "name": "Lifecycle form", "slug": "lifecycle-form"}
    invalid = admin.post("/api/admin/forms", json={**payload, "requester_layout": ["missing"]})
    assert invalid.status_code == 422

    created = admin.post("/api/admin/forms", json=payload)
    assert created.status_code == 201, created.text
    form = created.json()
    updated = admin.patch(f"/api/admin/forms/{form['id']}", json={
        **payload, "name": "Lifecycle form renamed", "version": form["version"], "published": False,
    })
    assert updated.status_code == 200, updated.text
    versions = admin.get(f"/api/admin/forms/{form['id']}/versions")
    assert versions.status_code == 200
    assert len(versions.json()) == 2
    first = next(item for item in versions.json() if item["version"] == 1)
    restored = admin.post(f"/api/admin/forms/{form['id']}/versions/{first['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["name"] == "Lifecycle form"

    archived = admin.delete(f"/api/admin/forms/{form['id']}")
    assert archived.status_code == 200
    restored_archive = admin.post(f"/api/admin/forms/{form['id']}/unarchive")
    assert restored_archive.status_code == 200
    assert restored_archive.json()["archived_at"] is None
    assert restored_archive.json()["published"] is False


def test_custom_field_privacy_masking_role_access_and_reporting_controls(admin,client):
    payload={**CHANGE_FORM,"name":"Privacy controlled request","slug":"privacy-controlled-request"}
    payload["fields"]=[
        {"id":"reference","key":"reference","label":"Reference","type":"short_text","required":True,"help":"","options":[],"classification":"public","mask_value":True,"reportable":True},
        {"id":"internal","key":"internal_context","label":"Internal context","type":"short_text","required":True,"help":"","options":[],"classification":"internal","reportable":True},
        {"id":"restricted","key":"restricted_value","label":"Restricted value","type":"short_text","required":True,"help":"","options":[],"classification":"restricted","access_roles":["manager","admin","auditor"],"reportable":False,"retention_days":30},
    ]
    form=admin.post("/api/admin/forms",json=payload);assert form.status_code==201,form.text
    csrf=login_as(client,"user1");client.headers.update({"X-CSRF-Token":csrf})
    created=client.post(f"/api/forms/{form.json()['id']}/submit",json={"subject":"Privacy behavior test","values":{"reference":"ABCDEF1234","internal_context":"diagnostic","restricted_value":"regulated"}})
    assert created.status_code==201,created.text;ticket=created.json()["ticket"]
    assert ticket["custom_data"]=={"reference":"••••1234"}
    detail=client.get(f"/api/tickets/{ticket['id']}").json();assert "internal_context" not in detail["custom_data"]
    manager_csrf=login_as(client,"manager");client.headers.update({"X-CSRF-Token":manager_csrf})
    staff=client.get(f"/api/tickets/{ticket['id']}").json();assert staff["custom_data"]["internal_context"]=="diagnostic" and staff["custom_data"]["restricted_value"]=="regulated"
    csrf_admin=login_as(client,"admin");client.headers.update({"X-CSRF-Token":csrf_admin})
    blocked=client.post("/api/admin/report-definitions",json={"name":"Unsafe restricted report","description":"Must be rejected","active":True,"configuration":{"columns":["number","custom.restricted_value"],"filters":[],"group_by":""}})
    assert blocked.status_code==422 and "unsupported column" in blocked.text


def test_asset_field_attaches_full_asset_context_for_technician(admin):
    asset = admin.get("/api/bootstrap").json()["assets"][0]
    payload = {**CHANGE_FORM, "name": "Asset Context Request", "slug": "asset-context-request"}
    payload["fields"] = [{
        "id": "asset", "key": "affected_asset", "label": "Affected asset", "type": "asset",
        "required": True, "help": "", "options": [], "width": "full", "placeholder": "Choose an asset",
    }]
    created = admin.post("/api/admin/forms", json=payload)
    assert created.status_code == 201, created.text
    submitted = admin.post(f"/api/forms/{created.json()['id']}/submit", json={
        "subject": "Test selected asset context", "values": {"affected_asset": str(asset["id"])},
        "asset_ids": [asset["id"]],
    })
    assert submitted.status_code == 201, submitted.text
    ticket = submitted.json()["ticket"]
    assert "Asset information" in ticket["description"]
    assert f"Asset tag: {asset['asset_tag']}" in ticket["description"]
    assert ticket["assets"][0]["asset_type"]
    assert "status" in ticket["assets"][0]


def test_drafts_and_templates_stay_out_of_service_catalog(admin):
    draft_payload = {
        **CHANGE_FORM,
        "name": "Studio Draft Visibility Test",
        "slug": "studio-draft-visibility-test",
        "published": False,
        "is_template": False,
    }
    draft = admin.post("/api/admin/forms", json=draft_payload)
    assert draft.status_code == 201, draft.text
    assert draft.json()["published"] is False

    template_payload = {
        **CHANGE_FORM,
        "name": "Studio Reusable Template Test",
        "slug": "studio-reusable-template-test",
        "published": False,
        "is_template": True,
    }
    template = admin.post("/api/admin/forms", json=template_payload)
    assert template.status_code == 201, template.text
    assert template.json()["is_template"] is True

    catalog = admin.get("/api/forms")
    assert catalog.status_code == 200
    catalog_ids = {form["id"] for form in catalog.json()}
    assert draft.json()["id"] not in catalog_ids
    assert template.json()["id"] not in catalog_ids

    invalid = admin.post("/api/admin/forms", json={
        **template_payload,
        "name": "Invalid Published Template",
        "slug": "invalid-published-template",
        "published": True,
    })
    assert invalid.status_code == 422
    assert "cannot be published" in invalid.text


def test_all_fields_test_form_definition_is_complete():
    migration = runpy.run_path(str(Path("migrations/versions/0007_form_templates_and_test_form.py")))
    test_fields = migration["TEST_FIELDS"]
    field_types = {field["type"] for field in test_fields}
    assert {"section", "short_text", "long_text", "email", "phone", "number", "date", "time",
            "select", "choice_cards", "radio", "multi_select", "checkbox", "user", "asset"} <= field_types
    dropdown = next(field for field in test_fields if field["type"] == "select")
    assert len(dropdown["options"]) >= 5


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
    assert all("change" in row["request_type"].lower() for row in body["rows"]), body["rows"]
