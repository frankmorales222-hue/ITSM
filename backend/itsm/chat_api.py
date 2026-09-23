from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import Role, Ticket, TicketChatSession, TicketHistory, TicketMessage, TicketStatus, User, now
from .security import current_user
from .services import audit, notify
from .teams_support import create_support_meeting

router = APIRouter(prefix="/api", tags=["ticket-chat"])
OPEN_TICKET_STATUSES = {status for status in TicketStatus if status not in {TicketStatus.CLOSED, TicketStatus.CANCELLED}}
OPEN_CHAT_STATUSES = {"requested", "active"}


class ChatMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


def _ticket(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket


def _session(db: Session, session_id: int) -> TicketChatSession:
    session = db.get(TicketChatSession, session_id)
    if not session:
        raise HTTPException(404, "Chat not found")
    return session


def _participant(db: Session, session: TicketChatSession, user: User) -> Ticket:
    ticket = _ticket(db, session.ticket_id)
    if user.id not in {ticket.requester_id, ticket.assigned_user_id}:
        raise HTTPException(404, "Chat not found")
    return ticket


def _message_dict(message: TicketMessage) -> dict:
    return {
        "id": message.id,
        "body": message.body,
        "author_id": message.author_id,
        "author": message.author.display_name if message.author else "Northstar Desk",
        "created_at": message.created_at,
        "source": message.source,
    }


def _session_dict(db: Session, session: TicketChatSession, include_messages: bool = False) -> dict:
    ticket = db.get(Ticket, session.ticket_id)
    data = {
        "id": session.id,
        "ticket_id": session.ticket_id,
        "ticket_number": ticket.number if ticket else "",
        "requester_id": ticket.requester_id if ticket else None,
        "requester": ticket.requester.display_name if ticket else "",
        "assigned_user_id": ticket.assigned_user_id if ticket else None,
        "assigned_user": ticket.assigned_user.display_name if ticket and ticket.assigned_user else None,
        "requested_by_id": session.requested_by_id,
        "status": session.status,
        "requested_at": session.requested_at,
        "accepted_at": session.accepted_at,
        "closed_at": session.closed_at,
        "last_activity_at": session.last_activity_at,
    }
    if include_messages:
        messages = db.scalars(select(TicketMessage).where(
            TicketMessage.chat_session_id == session.id,
            TicketMessage.kind == "public",
        ).order_by(TicketMessage.id)).all()
        data["messages"] = [_message_dict(message) for message in messages]
    return data


@router.get("/tickets/{ticket_id}/chat")
def ticket_chat(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = _ticket(db, ticket_id)
    if user.id not in {ticket.requester_id, ticket.assigned_user_id}:
        raise HTTPException(404, "Chat not found")
    session = db.scalar(select(TicketChatSession).where(
        TicketChatSession.ticket_id == ticket.id,
    ).order_by(TicketChatSession.id.desc()))
    return {"session": _session_dict(db, session, True) if session else None}


@router.post("/tickets/{ticket_id}/chat/request")
def request_chat(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = _ticket(db, ticket_id)
    if user.id not in {ticket.requester_id, ticket.assigned_user_id}:
        raise HTTPException(404, "Ticket not found")
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise HTTPException(409, "Live help is not available for a closed ticket")
    if not ticket.assigned_user_id:
        raise HTTPException(409, "A technician must be assigned before live help can start")
    existing = db.scalar(select(TicketChatSession).where(
        TicketChatSession.ticket_id == ticket.id,
        TicketChatSession.status.in_(OPEN_CHAT_STATUSES),
    ).order_by(TicketChatSession.id.desc()))
    if existing:
        return _session_dict(db, existing, True)
    session = TicketChatSession(
        ticket_id=ticket.id,
        requested_by_id=user.id,
        assigned_user_id=ticket.assigned_user_id,
        status="requested",
        requested_at=now(),
        last_activity_at=now(),
    )
    db.add(session)
    db.flush()
    requester_started = user.id == ticket.requester_id
    counterpart_id = ticket.assigned_user_id if requester_started else ticket.requester_id
    marker = TicketMessage(
        ticket_id=ticket.id,
        author_id=user.id,
        chat_session_id=session.id,
        body=f"{user.display_name} started a live-support conversation.",
        kind="public",
        source="live_chat",
    )
    db.add(marker)
    db.add(TicketHistory(ticket_id=ticket.id, event_type="chat_requested", actor_id=user.id,
                         new_value={"chat_session_id": session.id}))
    notify(db, counterpart_id, "chat.requested",
           f"[{ticket.number}] Live support invitation", f"{user.display_name} invited you to live support.",
           ticket.id, email=not requester_started)
    audit(db, "chat.requested", "ticket_chat_session", session.id, user.id,
          new={"ticket_id": ticket.id, "assigned_user_id": ticket.assigned_user_id})
    db.commit()
    return _session_dict(db, session, True)


@router.get("/chat/invitations")
def chat_invitations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == Role.END_USER:
        conditions = (Ticket.requester_id == user.id, TicketChatSession.requested_by_id != user.id)
    else:
        conditions = (Ticket.assigned_user_id == user.id, TicketChatSession.requested_by_id != user.id)
    sessions = db.scalars(select(TicketChatSession).join(Ticket, Ticket.id == TicketChatSession.ticket_id).where(
        *conditions, TicketChatSession.status == "requested",
    ).order_by(TicketChatSession.requested_at)).all()
    return [_session_dict(db, session) for session in sessions]


@router.post("/chat/{session_id}/accept")
def accept_chat(session_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _session(db, session_id)
    ticket = _participant(db, session, user)
    if user.id == session.requested_by_id:
        raise HTTPException(404, "Chat not found")
    if session.status == "closed":
        raise HTTPException(409, "Chat is closed")
    if session.status == "requested":
        session.status = "active"
        session.accepted_by_id = user.id
        session.accepted_at = now()
        session.last_activity_at = now()
        db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id, chat_session_id=session.id,
                             body=f"{user.display_name} joined the live chat.", kind="public", source="live_chat"))
        db.add(TicketHistory(ticket_id=ticket.id, event_type="chat_accepted", actor_id=user.id,
                             new_value={"chat_session_id": session.id}))
        audit(db, "chat.accepted", "ticket_chat_session", session.id, user.id, new={"ticket_id": ticket.id})
        db.commit()
    return _session_dict(db, session, True)


@router.get("/chat/{session_id}/messages")
def chat_messages(session_id: int, after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _session(db, session_id)
    _participant(db, session, user)
    messages = db.scalars(select(TicketMessage).where(
        TicketMessage.chat_session_id == session.id,
        TicketMessage.kind == "public",
        TicketMessage.id > after_id,
    ).order_by(TicketMessage.id).limit(limit)).all()
    return {"status": session.status, "messages": [_message_dict(message) for message in messages]}


@router.post("/chat/{session_id}/messages")
def send_chat_message(session_id: int, payload: ChatMessageIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    session = _session(db, session_id)
    ticket = _participant(db, session, user)
    if session.status not in OPEN_CHAT_STATUSES or ticket.status not in OPEN_TICKET_STATUSES:
        raise HTTPException(409, "Chat is closed")
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, "Message cannot be blank")
    duplicate = db.scalar(select(TicketMessage).where(
        TicketMessage.chat_session_id == session.id,
        TicketMessage.client_message_id == payload.client_message_id,
    ))
    if duplicate:
        return _message_dict(duplicate)
    latest = db.scalar(select(TicketMessage).where(
        TicketMessage.chat_session_id == session.id,
        TicketMessage.author_id == user.id,
        TicketMessage.client_message_id.is_not(None),
    ).order_by(TicketMessage.created_at.desc()))
    if latest:
        created = latest.created_at if latest.created_at.tzinfo else latest.created_at.replace(tzinfo=timezone.utc)
        if (now() - created).total_seconds() < 0.75:
            raise HTTPException(429, "Please wait before sending another message")
    message = TicketMessage(ticket_id=ticket.id, author_id=user.id, chat_session_id=session.id,
                            client_message_id=payload.client_message_id, body=body,
                            kind="public", source="live_chat")
    db.add(message)
    session.last_activity_at = now()
    recipient_id = ticket.assigned_user_id if user.id == ticket.requester_id else ticket.requester_id
    notify(db, recipient_id, "chat.message", f"[{ticket.number}] New live-chat message",
           "A new secure live-chat message is available in the ticket.", ticket.id)
    db.add(TicketHistory(ticket_id=ticket.id, event_type="chat_message", actor_id=user.id,
                         new_value={"chat_session_id": session.id, "source": "live_chat"}))
    audit(db, "chat.message", "ticket_chat_session", session.id, user.id,
          new={"ticket_id": ticket.id, "recipient_id": recipient_id})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(select(TicketMessage).where(
            TicketMessage.chat_session_id == session.id,
            TicketMessage.client_message_id == payload.client_message_id,
        ))
        if duplicate:
            return _message_dict(duplicate)
        raise
    db.refresh(message)
    return _message_dict(message)


@router.post("/chat/{session_id}/close")
def close_chat(session_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _session(db, session_id)
    ticket = _participant(db, session, user)
    if session.status != "closed":
        session.status = "closed"
        session.closed_at = now()
        session.last_activity_at = now()
        db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id, chat_session_id=session.id,
                             body=f"{user.display_name} ended the live chat. The transcript remains part of this ticket.",
                             kind="public", source="live_chat"))
        db.add(TicketHistory(ticket_id=ticket.id, event_type="chat_closed", actor_id=user.id,
                             new_value={"chat_session_id": session.id}))
        audit(db, "chat.closed", "ticket_chat_session", session.id, user.id, new={"ticket_id": ticket.id})
        db.commit()
    return _session_dict(db, session, True)


@router.post("/tickets/{ticket_id}/teams-session")
def start_teams_session(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = _ticket(db, ticket_id)
    if ticket.assigned_user_id != user.id or user.role == Role.END_USER:
        raise HTTPException(404, "Ticket not found")
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise HTTPException(409, "A Teams session cannot be created for a closed ticket")
    try:
        join_url = create_support_meeting(db, ticket, user)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Microsoft Teams could not create the support session") from exc
    db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id,
                         body=f"{user.display_name} created a Microsoft Teams support session: {join_url}",
                         kind="public", source="teams"))
    db.add(TicketHistory(ticket_id=ticket.id, event_type="teams_session_created", actor_id=user.id,
                         new_value={"provider": "Microsoft Teams"}))
    notify(db, ticket.requester_id, "teams.session_created",
           f"[{ticket.number}] Join your Teams support session",
           f"Your technician created a secure Microsoft Teams support session. Join here: {join_url}",
           ticket.id, email=True)
    audit(db, "teams.session_created", "ticket", ticket.id, user.id,
          new={"provider": "Microsoft Teams", "requester_id": ticket.requester_id})
    db.commit()
    return {"join_url": join_url}
