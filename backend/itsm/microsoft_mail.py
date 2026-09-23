"""Microsoft 365 shared-mailbox transport using Microsoft Graph.

The connection stores only organization configuration.  The deployment-level
application credential is encrypted by the existing provider credential store.
Graph application permissions are used so the background worker can process a
shared mailbox without a technician remaining signed in.
"""
from __future__ import annotations

from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .credential_store import get_integration_secret
from .models import IntegrationConnection, IntegrationLog, now

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def connected_mailbox(db: Session) -> IntegrationConnection | None:
    return db.scalar(select(IntegrationConnection).where(
        IntegrationConnection.kind == "email",
        IntegrationConnection.provider == "Microsoft 365",
        IntegrationConnection.enabled.is_(True),
        IntegrationConnection.status == "Connected",
        IntegrationConnection.archived_at.is_(None),
    ).order_by(IntegrationConnection.id))


def _application_credentials(db: Session) -> tuple[str, str]:
    client_id = settings.microsoft_client_id or get_integration_secret(db, "platform:microsoft", "client_id") or ""
    client_secret = settings.microsoft_client_secret or get_integration_secret(db, "platform:microsoft", "client_secret") or ""
    if not client_id or not client_secret:
        raise RuntimeError("Microsoft application credentials are not configured")
    return client_id, client_secret


def mailbox_address(connection: IntegrationConnection) -> str:
    address = str((connection.configuration or {}).get("mailbox", "")).strip().lower()
    if not address:
        raise RuntimeError("The Microsoft 365 connection needs a shared mailbox address")
    return address


def access_token(db: Session, connection: IntegrationConnection) -> str:
    tenant = str((connection.configuration or {}).get("tenant_id", "")).strip()
    if not tenant:
        raise RuntimeError("The Microsoft 365 tenant was not discovered during authorization")
    client_id, client_secret = _application_credentials(db)
    response = httpx.post(
        f"https://login.microsoftonline.com/{quote(tenant, safe='')}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Microsoft did not return an application access token")
    return token


def _headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def test_connection(db: Session, connection: IntegrationConnection) -> dict:
    token = access_token(db, connection)
    mailbox = mailbox_address(connection)
    response = httpx.get(
        f"{GRAPH_ROOT}/users/{quote(mailbox, safe='')}/mailFolders/inbox",
        headers=_headers(token), timeout=30,
    )
    response.raise_for_status()
    connection.last_attempt_at = now()
    connection.last_success_at = now()
    connection.last_error = ""
    connection.status = "Connected"
    db.add(IntegrationLog(connection_id=connection.id, level="success", event="mailbox.test_succeeded",
                          details={"mailbox": mailbox, "message": "Microsoft Graph mailbox access verified."}))
    return {"mailbox": mailbox, "folder": response.json().get("displayName", "Inbox")}


def send_notification(db: Session, connection: IntegrationConnection, recipient: str,
                      subject: str, body: str, ticket_url: str | None = None) -> str | None:
    """Send mail and return its RFC Message-ID for reliable reply threading.

    Graph's convenient ``sendMail`` action returns no message resource, which
    means a later reply cannot be joined by ``In-Reply-To`` when a mail client
    rewrites the subject.  Creating a draft first gives us the provider's
    internetMessageId; the worker records that ID against the ticket before the
    next mailbox poll.
    """
    token = access_token(db, connection)
    mailbox = mailbox_address(connection)
    footer = f"\n\nOpen this request in Northstar Desk: {ticket_url}" if ticket_url else ""
    response = httpx.post(
        f"{GRAPH_ROOT}/users/{quote(mailbox, safe='')}/messages",
        headers=_headers(token, **{"Content-Type": "application/json"}),
        json={
            "subject": subject,
            "body": {"contentType": "Text", "content": f"{body}{footer}"},
            "toRecipients": [{"emailAddress": {"address": recipient}}],
            "internetMessageHeaders": [
                {"name": "X-Northstar-Desk", "value": "notification"},
                {"name": "X-Auto-Response-Suppress", "value": "All"},
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    draft = response.json()
    draft_id = str(draft.get("id") or "").strip()
    if not draft_id:
        raise RuntimeError("Microsoft Graph did not return the outbound draft identifier")
    internet_message_id = str(draft.get("internetMessageId") or "").strip() or None
    sent = httpx.post(
        f"{GRAPH_ROOT}/users/{quote(mailbox, safe='')}/messages/{quote(draft_id, safe='')}/send",
        headers=_headers(token), timeout=30,
    )
    sent.raise_for_status()
    return internet_message_id


def unread_messages(db: Session, connection: IntegrationConnection, limit: int = 25) -> list[dict]:
    """Return recent inbox messages, including items Outlook marked read.

    Processing is idempotent by the Graph/message IDs stored in EmailMessage, so
    reading a reply in Outlook can no longer prevent it from reaching its ticket.
    """
    token = access_token(db, connection)
    mailbox = mailbox_address(connection)
    response = httpx.get(
        f"{GRAPH_ROOT}/users/{quote(mailbox, safe='')}/mailFolders/inbox/messages",
        headers=_headers(token),
        params={"$select": "id,internetMessageId,subject,from,receivedDateTime", "$top": str(max(limit, 100)), "$orderby": "receivedDateTime desc"},
        timeout=30,
    )
    response.raise_for_status()
    return list(reversed(response.json().get("value", [])))


def message_mime(db: Session, connection: IntegrationConnection, message_id: str) -> bytes:
    token = access_token(db, connection)
    mailbox = mailbox_address(connection)
    response = httpx.get(
        f"{GRAPH_ROOT}/users/{quote(mailbox, safe='')}/messages/{quote(message_id, safe='')}/$value",
        headers=_headers(token), timeout=30,
    )
    response.raise_for_status()
    return response.content


def mark_read(db: Session, connection: IntegrationConnection, message_id: str) -> None:
    token = access_token(db, connection)
    mailbox = mailbox_address(connection)
    response = httpx.patch(
        f"{GRAPH_ROOT}/users/{quote(mailbox, safe='')}/messages/{quote(message_id, safe='')}",
        headers=_headers(token, **{"Content-Type": "application/json"}), json={"isRead": True}, timeout=30,
    )
    response.raise_for_status()
