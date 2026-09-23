from sqlalchemy import select

from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import AuditEvent, Ticket, TicketChatSession, TicketMessage, TicketStatus, User


def _login(client, username):
    client.cookies.clear()
    csrf = login_as(client, username)
    client.headers.update({"X-CSRF-Token": csrf})


def test_live_chat_is_persistent_and_limited_to_ticket_participants(client):
    _login(client, "user1")
    created = client.post("/api/tickets", json={
        "request_type": "Report an issue",
        "subject": "Live chat authorization test",
        "description": "Please help test the secure ticket live chat workflow.",
        "asset_ids": [], "impact": "Medium", "urgency": "Medium",
    })
    assert created.status_code == 201, created.text
    ticket = created.json()["ticket"]
    assert ticket["assigned_user_id"]

    requested = client.post(f"/api/tickets/{ticket['id']}/chat/request")
    assert requested.status_code == 200, requested.text
    session_id = requested.json()["id"]

    _login(client, "user2")
    assert client.get(f"/api/tickets/{ticket['id']}/chat").status_code == 404
    assert client.get(f"/api/chat/{session_id}/messages").status_code == 404

    with SessionLocal() as db:
        assigned = db.get(User, ticket["assigned_user_id"])
        assigned_username = assigned.username

    _login(client, assigned_username)
    invitations = client.get("/api/chat/invitations")
    assert invitations.status_code == 200
    assert any(item["id"] == session_id for item in invitations.json())
    accepted = client.post(f"/api/chat/{session_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "active"

    payload = {"body": "I am connected and ready to help.", "client_message_id": "test-message-00000001"}
    sent = client.post(f"/api/chat/{session_id}/messages", json=payload)
    assert sent.status_code == 200, sent.text
    duplicate = client.post(f"/api/chat/{session_id}/messages", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == sent.json()["id"]

    _login(client, "user1")
    transcript = client.get(f"/api/chat/{session_id}/messages")
    assert transcript.status_code == 200
    assert any(item["body"] == payload["body"] for item in transcript.json()["messages"])
    closed = client.post(f"/api/chat/{session_id}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert client.post(f"/api/chat/{session_id}/messages", json={
        "body": "This must not be accepted.", "client_message_id": "test-message-00000002",
    }).status_code == 409

    with SessionLocal() as db:
        saved = db.get(TicketChatSession, session_id)
        assert saved.status == "closed"
        rows = db.scalars(select(TicketMessage).where(TicketMessage.chat_session_id == session_id)).all()
        assert any(row.body == payload["body"] and row.source == "live_chat" for row in rows)
        audits = db.scalars(select(AuditEvent).where(AuditEvent.record_type == "ticket_chat_session",
                                                     AuditEvent.record_id == str(session_id))).all()
        assert audits
        assert all(payload["body"] not in str(event.new_value or {}) for event in audits)


def test_requester_explicit_close_instruction_closes_and_records_note(client):
    with SessionLocal() as db:
        requester = db.scalar(select(User).where(User.username == "user1"))
        ticket = db.scalar(select(Ticket).where(Ticket.requester_id == requester.id).order_by(Ticket.id))
        ticket.status = TicketStatus.WAITING_USER
        db.commit()
        ticket_id = ticket.id

    _login(client, "user1")
    vague = client.post(f"/api/tickets/{ticket_id}/messages", json={"body": "ok", "kind": "public"})
    assert vague.status_code == 200
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket.status != TicketStatus.CLOSED
        ticket.status = TicketStatus.WAITING_USER
        db.commit()

    explicit = client.post(f"/api/tickets/{ticket_id}/messages", json={
        "body": "It is okay to close the ticket", "kind": "public",
    })
    assert explicit.status_code == 200
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket.status == TicketStatus.CLOSED
        note = db.scalar(select(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.source == "system",
        ).order_by(TicketMessage.id.desc()))
        assert requester.display_name in note.body
        assert "closed the ticket at their request" in note.body


def test_requester_can_close_an_in_progress_ticket(client):
    with SessionLocal() as db:
        requester = db.scalar(select(User).where(User.username == "user1"))
        ticket = db.scalar(select(Ticket).where(Ticket.requester_id == requester.id).order_by(Ticket.id))
        ticket.status = TicketStatus.IN_PROGRESS
        db.commit()
        ticket_id = ticket.id
    _login(client, "user1")
    result = client.post(f"/api/tickets/{ticket_id}/messages", json={
        "body": "You can close the ticket", "kind": "public",
    })
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        assert db.get(Ticket, ticket_id).status == TicketStatus.CLOSED


def test_requester_close_also_closes_live_chat_session(client):
    with SessionLocal() as db:
        requester = db.scalar(select(User).where(User.username == "user1"))
        ticket = db.scalar(select(Ticket).where(
            Ticket.requester_id == requester.id,
            Ticket.status.notin_([TicketStatus.CLOSED, TicketStatus.CANCELLED]),
        ))
        ticket.status = TicketStatus.WAITING_USER
        ticket_id = ticket.id
    _login(client, "user1")
    session = client.post(f"/api/tickets/{ticket_id}/chat/request")
    assert session.status_code == 200
    session_id = session.json()["id"]
    result = client.post(f"/api/tickets/{ticket_id}/messages", json={
        "body": "You can close the ticket", "kind": "public",
    })
    assert result.status_code == 200
    with SessionLocal() as db:
        saved = db.get(TicketChatSession, session_id)
        assert saved.status == "closed"
        assert saved.closed_at is not None


def test_assigned_technician_can_invite_requester_to_live_chat(client):
    with SessionLocal() as db:
        ticket = db.scalar(select(Ticket).where(
            Ticket.assigned_user_id.is_not(None),
            Ticket.status.notin_([TicketStatus.CLOSED, TicketStatus.CANCELLED]),
        ))
        technician = db.get(User, ticket.assigned_user_id)
        ticket_id, requester_username = ticket.id, ticket.requester.username
    _login(client, technician.username)
    requested = client.post(f"/api/tickets/{ticket_id}/chat/request")
    assert requested.status_code == 200, requested.text
    session = requested.json()
    assert session["requested_by_id"] == technician.id
    _login(client, requester_username)
    invitations = client.get("/api/chat/invitations")
    assert any(item["id"] == session["id"] for item in invitations.json())
    accepted = client.post(f"/api/chat/{session['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"


def test_assigned_technician_can_create_teams_support_session(client, monkeypatch):
    with SessionLocal() as db:
        ticket = db.scalar(select(Ticket).where(Ticket.assigned_user_id.is_not(None),
                                                Ticket.status.notin_([TicketStatus.CLOSED, TicketStatus.CANCELLED])))
        technician = db.get(User, ticket.assigned_user_id)
        ticket_id = ticket.id
        username = technician.username
    monkeypatch.setattr("itsm.chat_api.create_support_meeting",
                        lambda db, ticket, organizer: "https://teams.microsoft.com/l/meetup-join/test-session")
    _login(client, username)
    result = client.post(f"/api/tickets/{ticket_id}/teams-session")
    assert result.status_code == 200, result.text
    assert result.json()["join_url"].startswith("https://teams.microsoft.com/")
    with SessionLocal() as db:
        marker = db.scalar(select(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.source == "teams",
        ).order_by(TicketMessage.id.desc()))
        assert marker and "teams.microsoft.com" in marker.body
