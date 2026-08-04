from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import Asset, AssetHistory, AutomationFailure, EmailMessage, Notification, Ticket, User
from sqlalchemy import func, select


def test_email_deduplication_and_threading(admin):
    first={"message_id":"<first-unique@example.test>","sender":"user1@example.test","subject":"Email-created issue","text_body":"A detailed issue sent through the configured mailbox.","headers":{},"attachments":[{"name":"screen.png","content_type":"image/png","size":1200}]}
    created=admin.post("/api/email/ingest",json=first);assert created.status_code==200 and created.json()["status"]=="created"
    duplicate=admin.post("/api/email/ingest",json=first);assert duplicate.json()["status"]=="duplicate"
    reply={"message_id":"<second-unique@example.test>","in_reply_to":first["message_id"],"references":[first["message_id"]],"sender":"user1@example.test","subject":"Completely changed subject","text_body":"This response must remain on the original ticket.","headers":{},"attachments":[]}
    threaded=admin.post("/api/email/ingest",json=reply);assert threaded.json()["status"]=="threaded" and threaded.json()["ticket_id"]==created.json()["ticket_id"]
    with SessionLocal() as db:
        message=db.scalar(select(EmailMessage).where(EmailMessage.message_id==first["message_id"]));assert message.attachment_metadata[0]["name"]=="screen.png"


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
