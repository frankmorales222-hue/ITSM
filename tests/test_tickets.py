from datetime import timedelta
from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import AuditEvent, Notification, Role, Team, Ticket, TicketMessage, TicketStatus, User, now
from itsm.services import priority_for, route_ticket, sla_dates
from sqlalchemy import select


def test_end_user_ticket_creation_and_visibility(client):
    csrf=login_as(client,"user1");client.headers.update({"X-CSRF-Token":csrf})
    created=client.post("/api/tickets",json={"request_type":"Report an issue","subject":"Keyboard stops responding","description":"The keyboard disconnects every few minutes during normal work.","asset_ids":[],"impact":"Medium","urgency":"High"})
    assert created.status_code==201
    ticket=created.json()["ticket"];assert ticket["number"].startswith("INC-") and ticket["priority"]=="High"
    own=client.get("/api/tickets?q=Keyboard stops").json();assert any(t["id"]==ticket["id"] for t in own)
    client.cookies.clear();csrf=login_as(client,"user2");client.headers.update({"X-CSRF-Token":csrf})
    assert client.get(f"/api/tickets/{ticket['id']}").status_code==404


def test_role_permissions(client):
    csrf=login_as(client,"user1");client.headers.update({"X-CSRF-Token":csrf})
    assert client.get("/api/admin/health").status_code==403
    assert client.get("/api/dashboard").status_code==403
    client.cookies.clear();csrf=login_as(client,"auditor");client.headers.update({"X-CSRF-Token":csrf})
    assert client.get("/api/dashboard").status_code==200
    assert client.post("/api/tickets",json={"request_type":"Other request","subject":"Test request","description":"This request should not be allowed for auditor."}).status_code==201


def test_assignment_and_least_active_routing():
    with SessionLocal() as db:
        requester=db.scalar(select(User).where(User.username=="user1"));team,tech,reason=route_ticket(db,"Hardware",requester)
        assert team.name=="Endpoint Services" and tech and "least-active" in reason
        tech.availability="Away";db.commit();team,none,reason=route_ticket(db,"Hardware",requester)
        assert none is None and "no available" in reason
        tech.availability="Available";db.commit()


def test_public_internal_and_restricted_notes(client):
    csrf=login_as(client,"tech1");client.headers.update({"X-CSRF-Token":csrf})
    ticket=client.get("/api/tickets?view=team").json()[0]
    assert client.post(f"/api/tickets/{ticket['id']}/messages",json={"body":"Public progress update","kind":"public"}).status_code==200
    assert client.post(f"/api/tickets/{ticket['id']}/messages",json={"body":"Internal diagnostic context","kind":"internal"}).status_code==200
    assert client.post(f"/api/tickets/{ticket['id']}/messages",json={"body":"Restricted context","kind":"restricted"}).status_code==403
    with SessionLocal() as db:
        kinds=set(db.scalars(select(TicketMessage.kind).where(TicketMessage.ticket_id==ticket["id"])).all());assert {"public","internal"}.issubset(kinds)
        assert db.scalar(select(Notification).where(Notification.ticket_id==ticket["id"],Notification.event=="technician.replied"))


def test_status_transition_requires_resolution(client):
    csrf=login_as(client,"manager");client.headers.update({"X-CSRF-Token":csrf})
    ticket=client.get("/api/tickets?view=open").json()[0]
    assert client.patch(f"/api/tickets/{ticket['id']}",json={"status":"Resolved"}).status_code==422
    done=client.patch(f"/api/tickets/{ticket['id']}",json={"resolution_summary":"Reconfigured the service and confirmed operation.","status":"Resolved"})
    assert done.status_code==200 and done.json()["status"]=="Resolved"


def test_priority_matrix_and_sla():
    assert priority_for("High","High")=="Critical"
    first,resolution=sla_dates("Critical",now());assert resolution-first==timedelta(hours=3)


def test_search_authorization(client):
    csrf=login_as(client,"user3");client.headers.update({"X-CSRF-Token":csrf})
    results=client.get("/api/tickets?q=sample request").json();assert results
    assert all(t["requester_id"]==client.get("/api/auth/me").json()["user"]["id"] for t in results)


def test_audit_created_for_ticket_change(client):
    csrf=login_as(client,"manager");client.headers.update({"X-CSRF-Token":csrf})
    ticket=client.get("/api/tickets?view=open").json()[0]
    assert client.patch(f"/api/tickets/{ticket['id']}",json={"category":"Network"}).status_code==200
    with SessionLocal() as db: assert db.scalar(select(AuditEvent).where(AuditEvent.action=="ticket.updated",AuditEvent.record_id==str(ticket["id"])))

