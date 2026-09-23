from datetime import timedelta
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .microsoft_mail import access_token
from .models import IntegrationConnection, Ticket, User, now

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def _microsoft_connection(db: Session) -> IntegrationConnection:
    connection = db.scalar(select(IntegrationConnection).where(
        IntegrationConnection.enabled.is_(True),
        IntegrationConnection.provider.in_(["Microsoft Entra ID", "Microsoft 365"]),
        IntegrationConnection.archived_at.is_(None),
    ).order_by(IntegrationConnection.kind == "directory", IntegrationConnection.id))
    if not connection or not (connection.configuration or {}).get("tenant_id"):
        raise RuntimeError("A connected Microsoft Entra ID or Microsoft 365 integration is required")
    return connection


def create_support_meeting(db: Session, ticket: Ticket, organizer: User) -> str:
    if not organizer.entra_object_id:
        raise RuntimeError("The assigned technician must sign in with Microsoft before creating a Teams session")
    connection = _microsoft_connection(db)
    token = access_token(db, connection)
    start = now()
    response = httpx.post(
        f"{GRAPH_ROOT}/users/{quote(organizer.entra_object_id, safe='')}/onlineMeetings",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "subject": f"Northstar support · {ticket.number}",
            "startDateTime": start.isoformat(),
            "endDateTime": (start + timedelta(hours=1)).isoformat(),
            "participants": {"attendees": [{
                "identity": {"user": {"displayName": ticket.requester.display_name}},
                "upn": ticket.requester.email,
            }]},
        },
        timeout=30,
    )
    response.raise_for_status()
    join_url = str(response.json().get("joinWebUrl") or "")
    hostname = (urlparse(join_url).hostname or "").lower()
    if not join_url.startswith("https://") or not (hostname == "teams.microsoft.com" or hostname.endswith(".teams.microsoft.com")):
        raise RuntimeError("Microsoft returned an invalid Teams meeting URL")
    return join_url
