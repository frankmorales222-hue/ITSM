from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import Asset, AssetHistory, AutomationFailure, EmailMessage, IntegrationSecret, Notification, Organization, Ticket, User
from sqlalchemy import func, select


def test_email_deduplication_and_threading(admin):
    first={"message_id":"<first-unique@example.test>","sender":"user1@example.test","subject":"Email-created issue","text_body":"A detailed issue sent through the configured mailbox.","headers":{},"attachments":[{"name":"screen.png","content_type":"image/png","size":1200}]}
    created=admin.post("/api/email/ingest",json=first);assert created.status_code==200 and created.json()["status"]=="created"
    duplicate=admin.post("/api/email/ingest",json=first);assert duplicate.json()["status"]=="duplicate"
    reply={"message_id":"<second-unique@example.test>","in_reply_to":first["message_id"],"references":[first["message_id"]],"sender":"user1@example.test","subject":"Completely changed subject","text_body":"This response must remain on the original ticket.","headers":{},"attachments":[]}
    threaded=admin.post("/api/email/ingest",json=reply);assert threaded.json()["status"]=="threaded" and threaded.json()["ticket_id"]==created.json()["ticket_id"]
    with SessionLocal() as db:
        message=db.scalar(select(EmailMessage).where(EmailMessage.message_id==first["message_id"]));assert message.attachment_metadata[0]["name"]=="screen.png"


def test_email_reply_threads_by_ticket_number_when_provider_headers_are_missing(admin):
    first={"message_id":"<subject-thread-first@example.test>","sender":"user1@example.test","subject":"Subject-threaded issue","text_body":"Create one ticket.","headers":{},"attachments":[]}
    created=admin.post("/api/email/ingest",json=first);assert created.status_code==200 and created.json()["status"]=="created"
    reply={"message_id":"<subject-thread-reply@example.test>","sender":"user1@example.test",
           "subject":f"Re: [{created.json()['ticket_number']}] Subject-threaded issue","text_body":"Append this to the same ticket.","headers":{},"attachments":[]}
    threaded=admin.post("/api/email/ingest",json=reply)
    assert threaded.status_code==200 and threaded.json()["status"]=="threaded"
    assert threaded.json()["ticket_id"]==created.json()["ticket_id"]


def test_automatic_email_ignored(admin):
    payload={"message_id":"<automatic@example.test>","sender":"user2@example.test","subject":"Automatic reply: away","text_body":"I am away.","headers":{"Auto-Submitted":"auto-replied"},"attachments":[]}
    assert admin.post("/api/email/ingest",json=payload).json()["status"]=="ignored_automatic"


def test_unknown_email_creates_failure(admin):
    payload={"message_id":"<unknown@example.test>","sender":"outsider@example.test","subject":"Unknown requester","text_body":"This sender has no local account.","headers":{},"attachments":[]}
    result=admin.post("/api/email/ingest",json=payload).json();assert result["status"]=="failed"
    failures=admin.get("/api/admin/failures").json();assert any(f["id"]==result["failure_id"] for f in failures)


def test_asset_uniqueness(admin):
    payload={"asset_tag":"AST-UNIQUE-TEST","hostname":"UNIQUE-HOST","serial_number":"UNIQUE-SERIAL","manufacturer":"Test","model":"Model","asset_type":"Laptop"}
    assert admin.post("/api/assets",json=payload).status_code==201
    payload["asset_tag"]="AST-UNIQUE-TEST-2"
    assert admin.post("/api/assets",json=payload).status_code==409


def test_asset_assignment_history(admin):
    with SessionLocal() as db:
        asset=db.scalar(select(Asset).where(Asset.asset_tag=="AST-10001"));employee_id=db.scalar(select(User.id).where(User.username=="user2"));asset_id=asset.id
    assert admin.post(f"/api/assets/{asset_id}/assign",json={"employee_id":2,"status":"Loaned"}).status_code==200
    with SessionLocal() as db: assert db.scalar(select(func.count(AssetHistory.id)).where(AssetHistory.asset_id==asset_id))>=2


def test_asset_create_edit_metadata_and_return(admin):
    payload={"asset_tag":"NATIVE-ASSET-001","name":"Native ITSM asset","manufacturer":"Dell","model":"Latitude","asset_type":"Laptop","category":"Computer","condition":"New"}
    created=admin.post("/api/assets",json=payload);assert created.status_code==201
    asset_id=created.json()["id"]
    edited=admin.patch(f"/api/assets/{asset_id}",json={"vendor":"Example Vendor","purchase_cost_cents":150000,"status":"Active"})
    assert edited.status_code==200 and edited.json()["vendor"]=="Example Vendor"
    metadata=admin.get("/api/assets/metadata").json();assert metadata["employees"] and metadata["locations"]
    employee_id=metadata["employees"][0]["id"]
    assert admin.post(f"/api/assets/{asset_id}/assign",json={"employee_id":employee_id,"status":"Active"}).status_code==200
    assert admin.post(f"/api/assets/{asset_id}/assign",json={"employee_id":None,"status":"Stock"}).status_code==200
    detail=admin.get(f"/api/assets/{asset_id}").json();assert detail["employee"] is None and detail["status"]=="Stock"


def test_automation_failure_resolution(admin):
    rows=admin.get("/api/admin/failures").json();open_item=next(x for x in rows if x["status"]=="Open")
    assert admin.post(f"/api/admin/failures/{open_item['id']}/resolve",json={"resolution_note":"Reviewed and corrected configuration."}).status_code==200
    updated=admin.get("/api/admin/failures").json();assert next(x for x in updated if x["id"]==open_item["id"])["status"]=="Resolved"


def test_health_dashboard_reports_and_notifications(admin):
    assert admin.get("/api/admin/health").json()["database"]=="Connected"
    dash=admin.get("/api/dashboard").json();assert dash["metrics"]["open"]>0 and dash["by_category"]
    assert admin.get("/api/reports/tickets.csv").headers["content-type"].startswith("text/csv")
    assert isinstance(admin.get("/api/notifications").json(),list)


def test_admin_configuration_is_editable_and_audited(admin):
    rows=admin.get("/api/admin/settings/email").json();assert rows and rows[0]["value"]["port"]==993
    value={**rows[0]["value"],"poll_seconds":90}
    assert admin.patch(f"/api/admin/settings/{rows[0]['id']}",json={"value":value}).status_code==200
    updated=admin.get("/api/admin/settings/email").json();assert updated[0]["value"]["poll_seconds"]==90
    events=admin.get("/api/audit").json();assert any(e["action"]=="configuration.changed" for e in events)


def test_employee_and_asset_support_context(admin):
    employee=admin.get("/api/employees/1");assert employee.status_code==200 and employee.json()["assets"] and "open_tickets" in employee.json()
    asset=admin.get("/api/assets/1");assert asset.status_code==200 and asset.json()["history"] and asset.json()["employee"]["name"]
    summary=admin.get("/api/assets/summary").json();assert summary["total"]>=25 and summary["assigned"]>0
    listed=admin.get("/api/assets?q=AST-10001").json();assert listed[0]["assigned_employee_email"]
    imported=admin.get("/api/assets?q=AP-LT-001").json()
    if imported: assert imported[0]["assetpilot_url"] is None


def test_assetpilot_one_click_launcher(admin, monkeypatch):
    from itsm import main as main_module

    monkeypatch.setattr(main_module.settings, "assetpilot_enabled", True)
    monkeypatch.setattr(main_module, "ensure_assetpilot_running", lambda: None)
    with SessionLocal() as db:
        asset=db.scalar(select(Asset).where(Asset.asset_tag=="AST-10001"))
        asset_id=asset.id; previous_source=asset.source; previous_source_id=asset.source_id
        asset.source="AssetPilot"; asset.source_id=42; db.commit()
    try:
        opened=admin.post(f"/api/integrations/assetpilot/open/{asset_id}")
        assert opened.status_code==200 and opened.json()["url"].endswith("/Assets/Edit?id=42")
        created=admin.post("/api/integrations/assetpilot/create")
        assert created.status_code==200 and created.json()["url"].endswith("/Assets/Create")
    finally:
        with SessionLocal() as db:
            asset=db.get(Asset,asset_id); asset.source=previous_source; asset.source_id=previous_source_id; db.commit()


def test_native_inventory_remains_available_when_assetpilot_is_disabled(admin, monkeypatch):
    from itsm import main as main_module

    monkeypatch.setattr(main_module.settings, "assetpilot_enabled", False)
    summary = admin.get("/api/assets/summary")
    assert summary.status_code == 200
    assert summary.json()["inventory_source"] == "Northstar Desk"
    assert summary.json()["integration_status"] == "Native ITSM inventory"
    assert summary.json()["assetpilot_url"] is None

    status = admin.get("/api/integrations/assetpilot/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert status.json()["running"] is False


def test_admin_updates_user_availability(admin):
    users=admin.get("/api/admin/users").json();tech=next(u for u in users if u["username"]=="tech2")
    changed=admin.patch(f"/api/admin/users/{tech['id']}",json={"availability":"Busy"});assert changed.status_code==200 and changed.json()["availability"]=="Busy"
    restored=admin.patch(f"/api/admin/users/{tech['id']}",json={"availability":"Available"});assert restored.json()["availability"]=="Available"


def test_organization_isolation_and_ringcentral_configuration(admin):
    organization=admin.get("/api/admin/organization").json();assert organization["name"]
    updated={"name":"Northstar Test Organization","timezone":"America/New_York","support_email":"support@example.test","support_phone":"+15555550100","logo_url":""}
    assert admin.patch("/api/admin/organization",json=updated).status_code==200
    ringcentral=admin.get("/api/admin/settings/ringcentral").json();assert ringcentral and ringcentral[0]["value"]["enabled"] is False
    secrets=admin.patch("/api/admin/integrations/ringcentral/secrets",json={"client_secret":"secret-value","jwt_credential":"jwt-value"})
    assert secrets.status_code==200 and secrets.json()["client_secret"] and secrets.json()["jwt_credential"]
    with SessionLocal() as db:
        encrypted=db.scalar(select(IntegrationSecret.encrypted_value).where(IntegrationSecret.name=="client_secret"))
        assert encrypted and "secret-value" not in encrypted
        second=Organization(name="Second Organization",slug="second",timezone="America/New_York")
        db.add(second);db.flush()
        db.add(Asset(organization_id=second.id,asset_tag="SECOND-ORG-ASSET",manufacturer="Test",model="Test",asset_type="Laptop"));db.commit()
    assert admin.get("/api/assets?q=SECOND-ORG-ASSET").json()==[]
    assert admin.patch("/api/admin/integrations/ringcentral/secrets",json={"clear":["client_secret","jwt_credential"]}).status_code==200
    restore={"name":organization["name"],"timezone":organization["timezone"],"support_email":organization["support_email"],"support_phone":organization["support_phone"],"logo_url":organization["logo_url"]}
    assert admin.patch("/api/admin/organization",json=restore).status_code==200
