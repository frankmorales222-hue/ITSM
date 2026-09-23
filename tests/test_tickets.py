from datetime import datetime, timedelta, timezone
from conftest import login_as
from itsm.database import SessionLocal
from itsm.main import ticket_dict
from itsm.models import AuditEvent, ConfigItem, Notification, Role, SystemState, Team, Ticket, TicketMessage, TicketStatus, User, now
from itsm.services import add_operational_minutes, priority_for, route_ticket, sla_dates
from sqlalchemy import select


def test_end_user_ticket_creation_and_visibility(client):
    csrf=login_as(client,"user1");client.headers.update({"X-CSRF-Token":csrf})
    created=client.post("/api/tickets",json={"request_type":"Report an issue","subject":"Keyboard stops responding","description":"The keyboard disconnects every few minutes during normal work.","asset_ids":[],"impact":"Medium","urgency":"High"})
    assert created.status_code==201
    ticket=created.json()["ticket"];assert ticket["number"].startswith("INC-") and ticket["priority"]=="High"
    assert ticket["assets"] and all(asset["assigned_email"].lower()=="user1@example.test" for asset in ticket["assets"])
    own=client.get("/api/tickets?q=Keyboard stops").json();assert any(t["id"]==ticket["id"] for t in own)
    client.cookies.clear();csrf=login_as(client,"user2");client.headers.update({"X-CSRF-Token":csrf})
    assert client.get(f"/api/tickets/{ticket['id']}").status_code==404


def test_role_permissions(client):
    csrf=login_as(client,"user1");client.headers.update({"X-CSRF-Token":csrf})
    assert client.get("/api/admin/health").status_code==403
    assert client.get("/api/dashboard").status_code==403
    client.cookies.clear();csrf=login_as(client,"auditor");client.headers.update({"X-CSRF-Token":csrf})
    assert client.get("/api/dashboard").status_code==200
    reports=client.get("/api/reports/support")
    assert reports.status_code==200
    payload=reports.json()
    assert {"kpis","open_items","expired_items","technicians","backlog_age","volume_trend"}.issubset(payload)
    assert len(payload["volume_trend"])==30
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


def test_ticket_detail_filters_messages_by_viewer_role_and_fails_closed():
    expected = {
        "user1": {"public"},
        "tech1": {"public", "internal"},
        "lead": {"public", "internal"},
        "manager": {"public", "internal", "restricted"},
        "admin": {"public", "internal", "restricted"},
        "auditor": {"public", "internal", "restricted"},
    }
    markers = {kind: f"visibility-regression-{kind}" for kind in ("public", "internal", "restricted")}
    with SessionLocal() as db:
        ticket = db.scalar(select(Ticket).where(Ticket.requester.has(username="user1")))
        author = db.scalar(select(User).where(User.username == "admin"))
        assert ticket is not None
        db.add_all([
            TicketMessage(ticket_id=ticket.id, author_id=author.id, body=body, kind=kind)
            for kind, body in markers.items()
        ])
        db.commit()

        for username, visible_kinds in expected.items():
            viewer = db.scalar(select(User).where(User.username == username))
            detail = ticket_dict(ticket, detail=True, viewer=viewer, db=db)
            visible_markers = {message["kind"] for message in detail["messages"] if message["body"] in markers.values()}
            assert visible_markers == visible_kinds

        assert ticket_dict(ticket, detail=True, viewer=None, db=db)["messages"] == []


def test_technician_can_open_ticket_directly_assigned_from_another_team(client):
    with SessionLocal() as db:
        technician=db.scalar(select(User).where(User.username=="tech1"))
        ticket=db.scalar(select(Ticket).where(Ticket.team_id!=technician.team_id,Ticket.restricted.is_(False)))
        assert ticket is not None
        original_assignee=ticket.assigned_user_id
        ticket.assigned_user_id=technician.id
        db.commit()
        ticket_id=ticket.id
    try:
        csrf=login_as(client,"tech1");client.headers.update({"X-CSRF-Token":csrf})
        mine=client.get("/api/tickets?view=mine")
        assert mine.status_code==200
        assert any(row["id"]==ticket_id for row in mine.json())
        detail=client.get(f"/api/tickets/{ticket_id}")
        assert detail.status_code==200,detail.text
        assert detail.json()["assigned_user_id"]==technician.id
    finally:
        with SessionLocal() as db:
            stored=db.get(Ticket,ticket_id)
            stored.assigned_user_id=original_assignee
            db.commit()


def test_bootstrap_assignment_selector_includes_every_assignable_staff_role(client):
    csrf=login_as(client,"admin");client.headers.update({"X-CSRF-Token":csrf})
    response=client.get("/api/bootstrap")
    assert response.status_code==200,response.text
    selectable={entry["id"] for entry in response.json()["technicians"]}
    with SessionLocal() as db:
        assignable=set(db.scalars(select(User.id).where(
            User.role.in_([Role.TECHNICIAN,Role.TEAM_LEAD,Role.MANAGER,Role.ADMIN]),
            User.active.is_(True),
        )).all())
    assert selectable==assignable


def test_status_transition_requires_resolution(client):
    csrf=login_as(client,"manager");client.headers.update({"X-CSRF-Token":csrf})
    ticket=client.get("/api/tickets?view=open").json()[0]
    assert client.patch(f"/api/tickets/{ticket['id']}",json={"status":"Resolved"}).status_code==422
    done=client.patch(f"/api/tickets/{ticket['id']}",json={"resolution_summary":"Reconfigured the service and confirmed operation.","status":"Resolved"})
    assert done.status_code==200 and done.json()["status"]=="Resolved"


def test_priority_matrix_and_sla():
    assert priority_for("High","High")=="Critical"
    first,resolution=sla_dates("Critical",now());assert resolution-first==timedelta(hours=3)


def test_operational_calendar_skips_closed_hours_weekends_and_holidays():
    calendar={"name":"US support","timezone":"UTC","days":["Monday","Tuesday","Wednesday","Thursday","Friday"],
              "start":"08:00","end":"17:00","holidays":["2026-08-17"]}
    start=datetime(2026,8,14,16,30,tzinfo=timezone.utc)  # Friday
    due=add_operational_minutes(start,120,calendar)
    assert due==datetime(2026,8,18,9,30,tzinfo=timezone.utc)


def test_sla_pauses_and_extends_due_dates_when_work_resumes(client):
    csrf=login_as(client,"manager");client.headers.update({"X-CSRF-Token":csrf})
    ticket=client.get("/api/tickets?view=open").json()[0]
    paused=client.patch(f"/api/tickets/{ticket['id']}",json={"status":"On Hold"})
    assert paused.status_code==200,paused.text
    with SessionLocal() as db:
        stored=db.get(Ticket,ticket["id"]);before=stored.resolution_due
        data=dict(stored.custom_data or {});data["sla_paused_at"]=(now()-timedelta(minutes=30)).isoformat();stored.custom_data=data;db.commit()
    resumed=client.patch(f"/api/tickets/{ticket['id']}",json={"status":"In Progress"})
    assert resumed.status_code==200,resumed.text
    with SessionLocal() as db:
        stored=db.get(Ticket,ticket["id"])
        assert stored.resolution_due>=before+timedelta(minutes=29)
        assert stored.custom_data["sla_total_paused_minutes"]>=29
        assert "sla_paused_at" not in stored.custom_data


def test_search_authorization(client):
    csrf=login_as(client,"user3");client.headers.update({"X-CSRF-Token":csrf})
    results=client.get("/api/tickets?q=sample request").json();assert results
    assert all(t["requester_id"]==client.get("/api/auth/me").json()["user"]["id"] for t in results)


def test_audit_created_for_ticket_change(client):
    csrf=login_as(client,"manager");client.headers.update({"X-CSRF-Token":csrf})
    ticket=client.get("/api/tickets?view=open").json()[0]
    assert client.patch(f"/api/tickets/{ticket['id']}",json={"category":"Network"}).status_code==200
    with SessionLocal() as db: assert db.scalar(select(AuditEvent).where(AuditEvent.action=="ticket.updated",AuditEvent.record_id==str(ticket["id"])))


def test_staff_creates_ticket_for_requester_and_counts_update(admin):
    bootstrap=admin.get("/api/bootstrap").json();requester=next(r for r in bootstrap["requesters"] if r["email"]=="user2@example.test")
    before=admin.get("/api/tickets/counts").json()["open"]
    created=admin.post("/api/tickets",json={"request_type":"Request access","subject":"Access request created by service desk","description":"Please provide access to the approved departmental resource.","requester_id":requester["id"]})
    assert created.status_code==201
    ticket=created.json()["ticket"];assert ticket["requester_email"]=="user2@example.test" and ticket["requester_department"]
    assert ticket["opened_by"]=="System Administrator"
    assert ticket["requester_snapshot"]["email"]=="user2@example.test"
    assert ticket["requester_snapshot"]["opened_by_email"]=="admin@example.test"
    assert ticket["requester_snapshot"]["submitted_at"]
    assert admin.get("/api/tickets/counts").json()["open"]==before+1


def test_ticket_automatically_links_assets_by_requester_email(admin):
    requester=next(r for r in admin.get("/api/bootstrap").json()["requesters"] if r["email"]=="user1@example.test")
    created=admin.post("/api/tickets",json={
        "request_type":"Report an issue","subject":"Automatic asset email matching",
        "description":"Verify assigned equipment is linked from the requester email.",
        "requester_id":requester["id"],"asset_ids":[],
    })
    assert created.status_code==201,created.text
    ticket=created.json()["ticket"]
    assert ticket["assets"]
    assert all(asset["assigned_email"].lower()==ticket["requester_email"].lower() for asset in ticket["assets"])


def test_round_robin_selects_next_available_technician():
    with SessionLocal() as db:
        requester=db.scalar(select(User).where(User.username=="user1"));config=db.scalar(select(ConfigItem).where(ConfigItem.section=="assignment"));original=dict(config.value)
        config.value={**original,"method":"round_robin"};state=db.get(SystemState,"round_robin_team_1")
        if state: db.delete(state)
        db.commit();_,first,first_reason=route_ticket(db,"General",requester);db.flush();_,second,second_reason=route_ticket(db,"General",requester)
        assert first and second and first.id!=second.id and "round-robin" in first_reason and "round-robin" in second_reason
        config.value=original;db.commit()
