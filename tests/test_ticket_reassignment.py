from sqlalchemy import select

from itsm.database import SessionLocal
from itsm.models import SupportQueue, Team, TeamMembership, TicketHistory, User


def test_staff_can_reassign_ticket_to_another_queue_and_eligible_technician(admin):
    bootstrap = admin.get("/api/bootstrap").json()
    technician = next(item for item in bootstrap["technicians"] if item["role"] == "technician")
    requester = next(item for item in bootstrap["requesters"] if item["role"] == "end_user")
    with SessionLocal() as db:
        destination = Team(name="Manual Transfer Team", queue_name="Manual Transfer Queue", key="manual-transfer", active=True, organization_id=1)
        db.add(destination)
        db.flush()
        db.add(TeamMembership(team_id=destination.id, user_id=technician["id"], active=True, organization_id=1))
        queue = SupportQueue(name="Manual Transfer Queue", team_id=destination.id, active=True, assignment_strategy="round_robin", organization_id=1)
        db.add(queue)
        db.commit()
        queue_id, team_id = queue.id, destination.id

    created = admin.post("/api/tickets", json={
        "request_type": "Other request", "subject": "Manual queue transfer verification",
        "description": "Confirm an authorized technician can move this ticket to another queue.",
        "requester_id": requester["id"],
    })
    assert created.status_code == 201, created.text
    ticket_id = created.json()["ticket"]["id"]

    response = admin.post(f"/api/tickets/{ticket_id}/reassign", json={
        "queue_id": queue_id, "assigned_user_id": technician["id"],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["team_id"] == team_id
    assert body["assigned_user_id"] == technician["id"]
    assert body["assigned_user"] == technician["display_name"]
    assert "Manually reassigned" in body["route_reason"]
    with SessionLocal() as db:
        assert db.scalar(select(TicketHistory).where(TicketHistory.ticket_id == ticket_id, TicketHistory.event_type == "reassigned"))


def test_reassignment_refuses_technician_outside_selected_queue(admin):
    bootstrap = admin.get("/api/bootstrap").json()
    requester = next(item for item in bootstrap["requesters"] if item["role"] == "end_user")
    user_ids = [item["id"] for item in bootstrap["technicians"]]
    with SessionLocal() as db:
        team = Team(name="Restricted Manual Queue Team", queue_name="Restricted Manual Queue", key="restricted-manual", active=True, organization_id=1)
        db.add(team)
        db.flush()
        db.add(TeamMembership(team_id=team.id, user_id=user_ids[0], active=True, organization_id=1))
        queue = SupportQueue(name="Restricted Manual Queue", team_id=team.id, active=True, organization_id=1)
        db.add(queue)
        db.commit()
        queue_id = queue.id

    ticket = admin.post("/api/tickets", json={
        "request_type": "Other request", "subject": "Manual queue eligibility verification",
        "description": "Confirm a technician outside of the queue cannot be selected.",
        "requester_id": requester["id"],
    }).json()["ticket"]
    response = admin.post(f"/api/tickets/{ticket['id']}/reassign", json={"queue_id": queue_id, "assigned_user_id": user_ids[-1]})
    assert response.status_code == 422
    assert "not eligible" in response.json()["detail"]
